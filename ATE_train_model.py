# import os
# from dotenv import load_dotenv
import pandas as pd
import numpy as np
from tabulate import tabulate

import torch
from torch.utils.data import Dataset
from transformers import AutoTokenizer, AutoModelForTokenClassification, DataCollatorForTokenClassification, TrainingArguments, Trainer, TrainerCallback

from sklearn.model_selection import train_test_split
from sklearn.metrics import precision_recall_fscore_support, accuracy_score

# load_dotenv()

# Paths & configuration
DATA_PATH = "SemEval_2014_dataset/Final_SemEval.csv"
MODEL_CHECKPOINT = "distilbert-base-uncased"
SAVED_MODEL_PATH = "aspect_extraction/best_model"

label2id = {
    "O": 0,
    "Begin-Asp": 1,
    "Inside-Asp": 2
}

id2label = {v: k for k, v in label2id.items()}
max_length = 128


# Class for preparing dataset for pytorch
class ATEDataset(Dataset):
    def __init__(self, data):
        self.data = data

    def __len__(self):
        return len(self.data)

    def __getitem__(self, idx):
        item = self.data[idx]
        return {
            "input_ids": torch.tensor(item["input_ids"], dtype=torch.long),
            "attention_mask": torch.tensor(item["attention_mask"], dtype=torch.long),
            "labels": torch.tensor(item["labels"], dtype=torch.long)
        }


# Class for training evaluation
class RealtimeLoggingCallback(TrainerCallback):
    def on_log(self, args, state, control, logs=None, **kwargs):
        if logs is None:
            return

        parts = []
        if "loss" in logs:
            parts.append(f"train_loss={logs['loss']:.4f}")
        if "eval_loss" in logs:
            parts.append(f"eval_loss={logs['eval_loss']:.4f}")
        if "eval_f1" in logs:
            parts.append(f"eval_f1={logs['eval_f1']:.4f}")

        if parts:
            step = state.global_step
            epoch = state.epoch
            print(f"[epoch={epoch:.2f} | step={step}] " + " | ".join(parts))


# Load pretrained DistilBert model
def load_model():
    tokenizer = AutoTokenizer.from_pretrained(MODEL_CHECKPOINT)
    return tokenizer


# Group the data for ATE model
def data_preparation(data_path):
    # Read final SemEval 2014 dataset after data preprocessing
    df = pd.read_csv(data_path)

    grouped = df.groupby("review").agg({
        "aspect": list,
        "start": list,
        "end": list
    }).reset_index()

    print("Unique sentences: ", len(grouped))
    print(grouped.head())
    return grouped


# Assigns IOB for finding aspects
def tokenize_align(tokenizer, data):
    tokenized = tokenizer(
        data["review"],
        return_offsets_mapping=True,
        truncation=True,
        max_length=max_length
    )

    offsets = tokenized["offset_mapping"]

    # Normal tokens default to O. Special tokens such as [CLS]/[SEP] use -100 so
    # Hugging Face ignores them in both the token-classification loss and metrics.
    labels = np.full(len(offsets), label2id["O"], dtype=int)
    for idx, (start, end) in enumerate(offsets):
        if start == 0 and end == 0:
            labels[idx] = -100

    for start_char, end_char in zip(data["start"], data["end"]):
        first_token = True
        for idx, (start, end) in enumerate(offsets):
            if start == 0 and end == 0:
                continue

            if not (end <= start_char or start >= end_char):
                if first_token:
                    labels[idx] = label2id["Begin-Asp"]
                    first_token = False
                else:
                    labels[idx] = label2id["Inside-Asp"]

    tokenized["labels"] = labels
    tokenized.pop("offset_mapping")
    return tokenized


# Apply IOB assignment function
def encode_data(tokenizer, data):
    tokenized = data.apply(lambda row: tokenize_align(tokenizer, row), axis=1)
    return tokenized


# Inspect sample sentence for BIO usage
def inspect_BIO_alignment(grouped_data, tokenized_data, tokenizer, sample_idx=0):
    print("\n" + "="*35 + " BIO ALIGNMENT INSPECTION " + "="*35)

    example_row = grouped_data.iloc[sample_idx]
    encoded_row = tokenized_data.iloc[sample_idx]

    input_ids = encoded_row["input_ids"]
    labels = encoded_row["labels"]
    tokens = tokenizer.convert_ids_to_tokens(input_ids)

    print(f"RAW TEXT (Index {sample_idx}):")
    print(example_row["review"])
    print(f"GROUND TRUTH ASPECTS: {example_row['aspect']}")
    print("\nTOKENS WITH ASSIGNED IOB LABELS:\n")

    for token, label_id in zip(tokens, labels):
        # Stop printing if we hit padding tokens to keep the console clean
        if token == "[PAD]":
            break
        label_name = "IGNORED" if label_id == -100 else id2label[label_id]
        print(f"{token:18} -> {label_name}")

    print("=" * 96 + "\n")


# Prepare data for pytorch usage
def prepare_datasets(tokenized_data, tokenizer):
    dataset_list = list(tokenized_data)
    train_data, val_data = train_test_split(dataset_list, test_size=0.1, random_state=42)
    print(f"Train size: {len(train_data)} | Validation size: {len(val_data)}")

    train_dataset = ATEDataset(train_data)
    val_dataset = ATEDataset(val_data)

    data_collator = DataCollatorForTokenClassification(
        tokenizer=tokenizer,
        padding=True,
        return_tensors="pt"
    )

    return train_dataset, val_dataset, data_collator


# Convert a BIO label sequence into exact token spans.
def bio_to_spans(label_ids):
    spans = set()
    span_start = None

    for token_idx, label_id in enumerate(label_ids):
        label = id2label[int(label_id)]

        if label == "Begin-Asp":
            if span_start is not None:
                spans.add((span_start, token_idx - 1))
            span_start = token_idx

        elif label == "Inside-Asp":
            # Repair an orphan I-tag by treating it as the beginning of a span.
            if span_start is None:
                span_start = token_idx

        else:  # O
            if span_start is not None:
                spans.add((span_start, token_idx - 1))
                span_start = None

    if span_start is not None:
        spans.add((span_start, len(label_ids) - 1))

    return spans


# Results evaluation
def evaluation_metrics(eval_pred):
    logits, labels = eval_pred
    predictions = np.argmax(logits, axis=-1)

    # Primary ATE evaluation: exact aspect-span precision/recall/F1.
    true_positive = 0
    false_positive = 0
    false_negative = 0

    # Secondary token-level metrics are retained for diagnostics.
    flat_true_labels = []
    flat_predictions = []

    for pred_sequence, label_sequence in zip(predictions, labels):
        valid_mask = label_sequence != -100
        true_sequence = label_sequence[valid_mask].astype(int).tolist()
        predicted_sequence = pred_sequence[valid_mask].astype(int).tolist()

        true_spans = bio_to_spans(true_sequence)
        predicted_spans = bio_to_spans(predicted_sequence)

        true_positive += len(true_spans & predicted_spans)
        false_positive += len(predicted_spans - true_spans)
        false_negative += len(true_spans - predicted_spans)

        flat_true_labels.extend(true_sequence)
        flat_predictions.extend(predicted_sequence)

    span_precision = (
        true_positive / (true_positive + false_positive)
        if (true_positive + false_positive) > 0 else 0.0
    )
    span_recall = (
        true_positive / (true_positive + false_negative)
        if (true_positive + false_negative) > 0 else 0.0
    )
    span_f1 = (
        2 * span_precision * span_recall / (span_precision + span_recall)
        if (span_precision + span_recall) > 0 else 0.0
    )

    token_precision, token_recall, token_macro_f1, _ = precision_recall_fscore_support(
        flat_true_labels,
        flat_predictions,
        average="macro",
        zero_division=0
    )
    token_accuracy = accuracy_score(flat_true_labels, flat_predictions)

    # f1/precision/recall deliberately refer to exact span metrics so Trainer
    # selects the checkpoint that is best at extracting complete aspect terms.
    return {
        "accuracy": token_accuracy,
        "f1": span_f1,
        "precision": span_precision,
        "recall": span_recall,
        "token_macro_f1": token_macro_f1,
        "token_macro_precision": token_precision,
        "token_macro_recall": token_recall,
    }


# Print model performance table
def performance_table(trainer):
    table_data = []

    for log in trainer.state.log_history:
        if "eval_loss" in log:
            epoch = log.get("epoch", 0.0)

            # Get the LAST training loss logged before this eval point
            train_loss = "N/A"
            for t_log in reversed(trainer.state.log_history):
                if "loss" in t_log and t_log.get("epoch", 0.0) <= epoch:
                    train_loss = t_log["loss"]
                    break

            table_data.append([
                f"{epoch:.1f}",
                f"{train_loss:.6f}" if isinstance(train_loss, float) else train_loss,
                f"{log.get('eval_loss', 0.0):.6f}",
                f"{log.get('eval_accuracy', 0.0):.6f}",
                f"{log.get('eval_f1', 0.0):.6f}",
                f"{log.get('eval_precision', 0.0):.6f}",
                f"{log.get('eval_recall', 0.0):.6f}",
                f"{log.get('eval_token_macro_f1', 0.0):.6f}"
            ])

    headers = [
        "Epoch", "Training Loss", "Validation Loss", "Token Accuracy",
        "Span F1", "Span Precision", "Span Recall", "Token Macro F1"
    ]
    print("\n" + "="*31 + " FINAL ATE TRAINING PERFORMANCE SUMMARY " + "="*31)
    print(tabulate(table_data, headers=headers, tablefmt="github"))
    print("=" * 112 + "\n")


# Model training
def train_model(train_dataset, val_dataset, data_collator, tokenizer):
    print("\nInitializing AutoModelForTokenClassification...")

    model = AutoModelForTokenClassification.from_pretrained(
        MODEL_CHECKPOINT,
        num_labels=len(label2id),
        id2label=id2label,
        label2id=label2id
    )

    training_args = TrainingArguments(
        output_dir="./aspect_extraction",
        eval_strategy="epoch",
        save_strategy="epoch",
        save_total_limit=3,
        learning_rate=2e-5,
        per_device_train_batch_size=16,
        per_device_eval_batch_size=16,
        num_train_epochs=3,
        weight_decay=0.01,
        logging_strategy="steps",
        logging_steps=25,
        load_best_model_at_end=True,
        metric_for_best_model="f1",
        greater_is_better=True,
        fp16=torch.cuda.is_available()
    )

    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=train_dataset,
        eval_dataset=val_dataset,
        data_collator=data_collator,
        compute_metrics=evaluation_metrics,
        callbacks=[RealtimeLoggingCallback]
    )

    print("Starting Model Training Loop...")
    trainer.train()

    print("Training finished! Saving the best model variant...")
    trainer.save_model("./aspect_extraction/best_model")
    tokenizer.save_pretrained("./aspect_extraction/best_model")

    performance_table(trainer)
    return trainer


# Extract aspects
def extract_aspects(text, model, tokenizer, max_length=128):
    model.eval()

    inputs = tokenizer(
        text,
        return_tensors="pt",
        return_offsets_mapping=True,
        truncation=True,
        max_length=max_length
    )

    # Move tensor items to the device the model is running on (CPU or GPU)
    inputs = {k: v.to(model.device) for k, v in inputs.items()}
    offset_mapping = inputs.pop("offset_mapping")

    with torch.no_grad():
        outputs = model(**inputs)

    logits = outputs.logits
    predictions = torch.argmax(logits, dim=-1).squeeze().tolist()
    offsets = offset_mapping.squeeze().tolist()
    id2label = model.config.id2label

    aspects = []
    current_aspect = ""

    for pred, (start, end) in zip(predictions, offsets):
        if start == 0 and end == 0:  # Skip special structural tokens
            continue

        label = id2label[pred]

        # FIXED: Matched label strings to your configured "Begin-Asp" and "Inside-Asp"
        if label == "Begin-Asp":
            if current_aspect:
                aspects.append(current_aspect.strip())
            current_aspect = text[start:end]

        elif label == "Inside-Asp":
            # Slices text and ensures proper word spacing if tokens are broken down.
            # If the model emits an orphan I-tag, start a new aspect instead of
            # silently dropping it.
            chunk = text[start:end]
            if current_aspect:
                if start > 0 and text[start-1] == " " and not current_aspect.endswith(" "):
                    current_aspect += " " + chunk
                else:
                    current_aspect += chunk
            else:
                current_aspect = chunk

        else:
            if current_aspect:
                aspects.append(current_aspect.strip())
                current_aspect = ""

    if current_aspect:
        aspects.append(current_aspect.strip())

    return aspects


# Testing aspect extraction model
def run_inference():
    print(f"\nLoading optimized model from {SAVED_MODEL_PATH} for evaluation testing...")

    # Load your custom saved checkpoints
    model_extr = AutoModelForTokenClassification.from_pretrained(SAVED_MODEL_PATH)
    tokenizer_extr = AutoTokenizer.from_pretrained(SAVED_MODEL_PATH)

    test_texts = [
        "The food was amazing but the service was terrible",
        "The setup was quick and easy, and the laptop runs smoothly right out of the box.",
        "Customer service was slow and the staff was unhelpful.",
        "The large screen allows me to have multiple windows open without having to carry a separate monitor and the number pad makes data entry in Excel faster.",
        "An excellent machine for the price. It struggles with extensive multitasking, but that's to be expected on a device like this.",
        "I love the display's details, and the keyboard works great. The sound quality is excellent while I'm working.",
        "The price is reasonable, the delivery was fast, and the packaging was damaged.",
        "It runs fast enough for school, but definitely not gaming.",
        "Laptop works great! Battery life exceeded my expectations. Love the way the keys sound when I type.",
        "Not bad at all."
    ]

    print("\n" + "="*40 + " RUNNING INFERENCE TEST " + "="*40)
    for i, text in enumerate(test_texts, 1):
        aspects = extract_aspects(text, model_extr, tokenizer_extr)

        print(f"EXAMPLE {i}: {text}")
        if aspects:
            # Cleans up the array into a nice comma-separated list
            print(f"EXTRACTED ASPECTS: {', '.join(aspects)}")
        else:
            print("EXTRACTED ASPECTS: none found")
        print("-" * 104)


# Main function
def main():
    tokenizer = load_model()
    grouped_data = data_preparation(DATA_PATH)
    tokenized_data = encode_data(tokenizer, grouped_data)

    inspect_BIO_alignment(grouped_data, tokenized_data, tokenizer, sample_idx=8)

    train_ds, val_ds, data_collator = prepare_datasets(tokenized_data, tokenizer)
    trainer = train_model(train_ds, val_ds, data_collator, tokenizer)

    run_inference()


if __name__ == "__main__":
    main()