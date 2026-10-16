import json
from pathlib import Path


def load_state(model_folder):
    folder = Path(model_folder)

    state_files = list(folder.rglob("trainer_state.json"))

    if not state_files:
        raise FileNotFoundError(
            f"No trainer_state.json found in {folder}"
        )

    state_file = max(
        state_files,
        key=lambda p: p.stat().st_mtime
    )

    with open(state_file, "r", encoding="utf-8") as f:
        return json.load(f)


def collect_epoch_logs(state):
    training = {}
    evaluation = {}

    for entry in state.get("log_history", []):
        epoch = entry.get("epoch")

        if epoch is None:
            continue

        epoch = int(round(epoch))

        # Training log
        if "loss" in entry and "eval_loss" not in entry:
            training[epoch] = entry

        # Validation/evaluation log
        if "eval_loss" in entry:
            evaluation[epoch] = entry

    return training, evaluation


def print_ate(model_folder):
    state = load_state(model_folder)

    training, evaluation = collect_epoch_logs(state)

    print()
    print("=" * 110)
    print("FINAL ATE TRAINING PERFORMANCE SUMMARY")
    print("=" * 110)

    header = (
        f"{'Epoch':>5} | "
        f"{'Training Loss':>13} | "
        f"{'Validation Loss':>15} | "
        f"{'Token Accuracy':>14} | "
        f"{'Span F1':>9} | "
        f"{'Span Precision':>14} | "
        f"{'Span Recall':>11} | "
        f"{'Token Macro F1':>14}"
    )

    print(header)
    print("-" * len(header))

    for epoch in sorted(evaluation):
        ev = evaluation[epoch]
        tr = training.get(epoch, {})

        print(
            f"{epoch:>5} | "
            f"{tr.get('loss', float('nan')):>13.4f} | "
            f"{ev['eval_loss']:>15.6f} | "
            f"{ev['eval_accuracy']:>14.6f} | "
            f"{ev['eval_f1']:>9.6f} | "
            f"{ev['eval_precision']:>14.6f} | "
            f"{ev['eval_recall']:>11.6f} | "
            f"{ev['eval_token_macro_f1']:>14.6f}"
        )

    print("=" * 110)
    print(
        f"Best checkpoint: {state.get('best_model_checkpoint')}"
    )
    print(
        f"Best Span F1:    {state.get('best_metric'):.6f}"
    )


def print_absa(model_folder):
    state = load_state(model_folder)

    training, evaluation = collect_epoch_logs(state)

    print()
    print("=" * 105)
    print("FINAL ABSA TRAINING PERFORMANCE SUMMARY")
    print("=" * 105)

    header = (
        f"{'Epoch':>5} | "
        f"{'Training Loss':>13} | "
        f"{'Validation Loss':>15} | "
        f"{'Accuracy':>10} | "
        f"{'Macro F1':>10} | "
        f"{'F1 Positive':>11} | "
        f"{'F1 Negative':>11} | "
        f"{'F1 Neutral':>10}"
    )

    print(header)
    print("-" * len(header))

    for epoch in sorted(evaluation):
        ev = evaluation[epoch]
        tr = training.get(epoch, {})

        print(
            f"{epoch:>5} | "
            f"{tr.get('loss', float('nan')):>13.4f} | "
            f"{ev['eval_loss']:>15.6f} | "
            f"{ev['eval_accuracy']:>10.6f} | "
            f"{ev['eval_f1']:>10.6f} | "
            f"{ev['eval_f1_positive']:>11.6f} | "
            f"{ev['eval_f1_negative']:>11.6f} | "
            f"{ev['eval_f1_neutral']:>10.6f}"
        )

    print("=" * 105)
    print(
        f"Best checkpoint: {state.get('best_model_checkpoint')}"
    )
    print(
        f"Best Macro F1:   {state.get('best_metric'):.6f}"
    )


print_ate("aspect_extraction")
print_absa("aspect_sentiment")