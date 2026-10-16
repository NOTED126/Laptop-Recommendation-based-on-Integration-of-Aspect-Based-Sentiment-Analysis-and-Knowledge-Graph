import pandas as pd
import numpy as np
from tabulate import tabulate

import torch
from torch.utils.data import Dataset
from transformers import AutoTokenizer, DataCollatorWithPadding, AutoModelForSequenceClassification, TrainingArguments, Trainer

from sklearn.model_selection import StratifiedGroupKFold
from sklearn.metrics import precision_recall_fscore_support, accuracy_score

from ATE_train_model import RealtimeLoggingCallback


# Paths & configuration
DATA_PATH = "SemEval_2014_dataset/Final_SemEval.csv"
MODEL_CHECKPOINT = "distilbert-base-uncased"
SAVED_MODEL_PATH = "aspect_sentiment/best_model"

label2id_sentiment = {
    "positive": 0,
    "negative": 1,
    "neutral": 2
}

id2label_sentiment = {v: k for k, v in label2id_sentiment.items()}
max_length = 128


# Class for preparing dataset for pytorch
class ABSADataset(Dataset):
    def __init__(self, data):
        self.data = data

    def __len__(self):
        return len(self.data)

    def __getitem__(self, idx):
        item = self.data[idx]
        # payload = {
        #     "input_ids": torch.tensor(item["input_ids"], dtype=torch.long),
        #     "attention_mask": torch.tensor(item["attention_mask"], dtype=torch.long),
        #     "labels": torch.tensor(item["labels"], dtype=torch.long)
        # }
        # if "token_type_ids" in item:
        #     payload["token_type_ids"] = torch.tensor(item["token_type_ids"], dtype=torch.long)

        # return payload
        return {
            "input_ids": torch.tensor(item["input_ids"], dtype=torch.long),
            "attention_mask": torch.tensor(item["attention_mask"], dtype=torch.long),
            # "token_type_ids": torch.tensor(item["token_type_ids"], dtype=torch.long),
            "labels": torch.tensor(item["labels"], dtype=torch.long),
        }


# Data preparation
def data_preparation_asc(data_path):
    # Read final SemEval 2014 dataset after data preprocessing
    df = pd.read_csv(data_path)
    df = df[["review", "aspect", "sentiment"]].copy()
    df = df.dropna().reset_index(drop=True)
    print(f"Total samples: {len(df)}")
    print(f"Unique sentiments: {df['sentiment'].unique()}")

    df["label"] = df["sentiment"].map(label2id_sentiment)
    # Error checking
    assert df["label"].isnull().sum() == 0, "Some labels were not mapped correctly!"

    print("\nLabel distribution:")
    print(df["sentiment"].value_counts())

    # Split by complete sentence, not by individual sentence-aspect rows.
    # A sentence may contain multiple aspects; row-level splitting can therefore
    # place one aspect from a sentence in training and another aspect from the
    # same sentence in validation, which leaks sentence context across splits.
    # StratifiedGroupKFold keeps each sentence in exactly one split while also
    # preserving the sentiment distribution more closely than a plain group split.
    group_key = df["review"].astype(str).str.strip()
    splitter = StratifiedGroupKFold(n_splits=10, shuffle=True, random_state=42)
    train_idx, val_idx = next(splitter.split(df, y=df["label"], groups=group_key))

    train_data = df.iloc[train_idx].reset_index(drop=True)
    val_data = df.iloc[val_idx].reset_index(drop=True)

    train_sentences = set(train_data["review"].astype(str).str.strip())
    val_sentences = set(val_data["review"].astype(str).str.strip())
    overlap = train_sentences & val_sentences
    assert not overlap, f"Sentence leakage detected across splits: {len(overlap)} overlapping sentences"

    print(f"\nTrain size: {len(train_data)} | Validation size: {len(val_data)}")
    print(f"Unique train sentences: {len(train_sentences)} | Unique validation sentences: {len(val_sentences)}")
    print("\nTraining sentiment distribution:")
    print(train_data["sentiment"].value_counts(normalize=True).sort_index())
    print("\nValidation sentiment distribution:")
    print(val_data["sentiment"].value_counts(normalize=True).sort_index())

    return train_data, val_data


# Tokenizing function
def tokenize_asc(data, tokenizer):
    encoded = tokenizer(
        data["review"],
        data["aspect"],
        truncation=True,
        max_length=max_length
    )
    encoded["labels"] = data["label"]
    return encoded


# Apply tokenization
def tokenizing_asc(tokenizer, train_data, val_data):
    print("\nTokenizing train split...")
    train_data_asc = [tokenize_asc(row, tokenizer) for _, row in train_data.iterrows()]
    print("Train data tokenization completed")
    print("\nTokenizing validation split...")
    val_data_asc = [tokenize_asc(row, tokenizer) for _, row in val_data.iterrows()]
    print("Validation data tokenization completed")

    return train_data_asc, val_data_asc


# Prepare data for pytorch usage
def prepare_datasets_asc(train_data, val_data, tokenizer):
    train_dataset_asc = ABSADataset(train_data)
    val_dataset_asc = ABSADataset(val_data)

    data_collator_asc = DataCollatorWithPadding(
        tokenizer=tokenizer,
        padding=True,
        return_tensors="pt"
    )

    return train_dataset_asc, val_dataset_asc, data_collator_asc


# Inspect sample sentence for sentence-aspect pair concatenation
def inspect_sequence_pairing(train_data_asc, tokenizer, sample_idx=0):
    print("\n" + "="*35 + " MODEL INPUT STRUCTURE INSPECTION " + "="*35)

    encoded = train_data_asc[sample_idx]
    tokens = tokenizer.convert_ids_to_tokens(encoded["input_ids"])
    # segments = encoded["token_type_ids"]

    # Track which segment we are currently printing to format the lines beautifully
    current_segment_id = 0
    line_buffer = []

    print(f"TOKENIZED PAIR STREAM (Index {sample_idx}):\n")

    # for token, seg_id in zip(tokens, segments):
    #     # Handle special structural tokens natively
    #     if token in ["[CLS]", "[SEP]"]:
    #         # If we were gathering words for a text block, print them out before the separator
    #         if line_buffer:
    #             segment_name = "Context Review" if current_segment == 0 else "Target Aspect "
    #             print(f"{segment_name:15}: {' '.join(line_buffer)}")
    #             line_buffer = []

    #         print(f"SPECIAL TOKEN   : {token}")
    #         current_segment = None  # Reset tracking state momentarily
    #     else:
    #         # Accumulate sub-word tokens belonging to the current sequence block
    #         current_segment = seg_id
    #         line_buffer.append(token)
    for token in tokens:
        if token in ["[CLS]", "[SEP]"]:
            # If we accumulated words, print them before displaying the separator token
            if line_buffer:
                segment_name = "Context Review" if current_segment_id == 0 else "Target Aspect "
                print(f"{segment_name:15}: {' '.join(line_buffer)}")
                line_buffer = []

            print(f"SPECIAL TOKEN   : {token}")

            # When we encounter the mid-sequence [SEP], switch our tracking context to the aspect segment
            if token == "[SEP]":
                current_segment_id = 1
        else:
            line_buffer.append(token)

    print("=" * 104 + "\n")


# Result evaluation
def evaluation_metrics_asc(eval_pred):
    logits, labels = eval_pred
    predictions = np.argmax(logits, axis=-1)

    precision, recall, f1_per_class, support = precision_recall_fscore_support(
        labels,
        predictions,
        average=None,
        labels=[0, 1, 2],
        zero_division=0
    )

    macro_f1 = np.mean(f1_per_class)
    acc = accuracy_score(labels, predictions)

    return {
        "accuracy": acc,
        "f1": macro_f1,              # for Trainer и callback
        "f1_positive": f1_per_class[0],
        "f1_negative": f1_per_class[1],
        "f1_neutral": f1_per_class[2],
    }


# Print model performance table
def performance_table_asc(trainer):
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

            # Append rows matching the columns in your image
            table_data.append([
                f"{epoch:.0f}",
                f"{float(train_loss):.6f}" if isinstance(train_loss, (float, str)) and str(train_loss).replace('.','',1).isdigit() else train_loss,
                f"{float(log.get('eval_loss', 0.0)):.6f}",
                f"{float(log.get('eval_accuracy', 0.0)):.6f}",
                f"{float(log.get('eval_f1', 0.0)):.6f}",
                f"{float(log.get('eval_f1_positive', 0.0)):.6f}",
                f"{float(log.get('eval_f1_negative', 0.0)):.6f}",
                f"{float(log.get('eval_f1_neutral', 0.0)):.6f}"
            ])

    headers = [
        "Epoch", "Training Loss", "Validation Loss", "Accuracy",
        "F1", "F1 Positive", "F1 Negative", "F1 Neutral"
    ]

    print("\n" + "="*40 + " FINAL ABSA TRAINING PERFORMANCE SUMMARY " + "="*39)
    print(tabulate(table_data, headers=headers, tablefmt="github"))
    print("=" * 120 + "\n")


# Model training
def train_model_asc(train_dataset, val_dataset, data_collator, tokenizer):
    print("\nInitializing AutoModelForSequenceClassification...")

    model = AutoModelForSequenceClassification.from_pretrained(
        MODEL_CHECKPOINT,
        num_labels=3,
        id2label=id2label_sentiment,
        label2id=label2id_sentiment
    )

    training_args = TrainingArguments(
        output_dir="./aspect_sentiment",
        eval_strategy="epoch",
        save_strategy="epoch",
        save_total_limit=2,
        learning_rate=2e-5,
        per_device_train_batch_size=16,
        per_device_eval_batch_size=16,
        num_train_epochs=3,
        weight_decay=0.01,
        logging_strategy="steps",
        logging_steps=50,
        load_best_model_at_end=True,
        metric_for_best_model="f1",
        greater_is_better=True,
        fp16=torch.cuda.is_available()
    )

    trainer_asc = Trainer(
        model=model,
        args=training_args,
        train_dataset=train_dataset,
        eval_dataset=val_dataset,
        data_collator=data_collator,
        compute_metrics=evaluation_metrics_asc,
        callbacks=[RealtimeLoggingCallback]
    )

    print("Starting Model Training Loop...")
    trainer_asc.train()

    print("Training finished! Saving the best model variant...")
    trainer_asc.save_model("./aspect_sentiment/best_model")
    tokenizer.save_pretrained("./aspect_sentiment/best_model")

    performance_table_asc(trainer_asc)
    return trainer_asc


# Predict sentiments
def predict_aspect_sentiment(text, aspect, model, tokenizer, max_length=128):
    inputs = tokenizer(
        text,
        aspect,
        return_tensors="pt",
        truncation=True,
        max_length=max_length
    )
    inputs = {k: v.to(model.device) for k, v in inputs.items()}
    with torch.no_grad():
        outputs = model(**inputs)

    logits = outputs.logits
    prediction = torch.argmax(logits, dim=-1).item()

    return model.config.id2label[prediction]


# Testing aspect sentiment model
def run_inference_asc():
    print(f"\nLoading optimized model from {SAVED_MODEL_PATH} for evaluation testing...")

    model_sent = AutoModelForSequenceClassification.from_pretrained(SAVED_MODEL_PATH)
    tokenizer_sent = AutoTokenizer.from_pretrained(SAVED_MODEL_PATH)

    # Set to evaluation mode and move to device
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model_sent.to(device)
    model_sent.eval()

    test_examples = [
        ("The pasta was delicious but the waiter was rude.", "pasta"),
        ("The pasta was delicious but the waiter was rude.", "waiter"),
        ("The laptop comes with 16GB RAM and a 512GB SSD.", "RAM"),
        ("An excellent machine for the price. It struggles with extensive multitasking, but that's to be expected on a device like this.", "price"),
        ("An excellent machine for the price. It struggles with extensive multitasking, but that's to be expected on a device like this.", "multitasking"),
        ("The app crashes every time I try to upload a file.", "app"),
        ("Compared to my old phone, the screen is brighter but heavier.", "screen"),
        ("Compared to my old phone, the screen is brighter but heavier.", "phone"),
        ("The design is okay, nothing special.", "design"),
        ("I expected more from the performance.", "performance"),
    ]

    print("\n" + "="*40 + " RUNNING INFERENCE TEST " + "="*40)
    for i, (text, aspect) in enumerate(test_examples, 1):
        sentiment = predict_aspect_sentiment(
            text,
            aspect,
            model_sent,
            tokenizer_sent
        )

        print(f"EXAMPLE {i}: {text}")
        print(f"ASPECT:   {aspect}")
        print(f"PREDICTED SENTIMENT: {sentiment.upper()}")
        print("-" * 104)


# Main function
def main():
    print(f"Loading tokenizer from {MODEL_CHECKPOINT}...")
    tokenizer = AutoTokenizer.from_pretrained(MODEL_CHECKPOINT)

    train_ds, val_ds = data_preparation_asc(DATA_PATH)
    train_data_asc, val_data_asc = tokenizing_asc(tokenizer, train_ds, val_ds)

    inspect_sequence_pairing(train_data_asc, tokenizer, sample_idx=0)

    train_ds_asc, val_ds_asc, data_collator_asc = prepare_datasets_asc(train_data_asc, val_data_asc, tokenizer)
    trainer = train_model_asc(train_ds_asc, val_ds_asc, data_collator_asc, tokenizer)

    run_inference_asc()

if __name__ == "__main__":
    main()