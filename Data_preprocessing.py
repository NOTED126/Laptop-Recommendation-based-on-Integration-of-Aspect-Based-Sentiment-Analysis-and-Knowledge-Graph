import pandas as pd
import matplotlib.pyplot as plt

# Dataset path
SEMEVAL_LAPTOP = "SemEval_2014_dataset/Laptop_Train_v2.csv"
SEMEVAL_RESTAURANT = "SemEval_2014_dataset/Restaurants_Train_v2.csv"
FINAL_DATA = "SemEval_2014_dataset/Final_SemEval.csv"

# Class for SemEval 2014 dataset modification
class SemEvalPipeline:
    def __init__(self, paths: dict):
        self.paths = paths
        self.datasets = {}
        self.combined_data = None
        self.final_data = None

    # Plot sentiment distribution
    def plot_sentiment_distribution(self, data, title="Sentiment Distribution"):
        sentiment_count = data["sentiment"].value_counts()
        fig, ax = plt.subplots(figsize=(6,6))
        bars = ax.bar(sentiment_count.index, sentiment_count.values)
        ax.bar_label(bars, padding=3)
        plt.xlabel("Sentiment")
        plt.ylabel("Count")
        plt.title(title)
        plt.show()

    # Load datasets
    def load_dataset(self):
        column_rename = {
            "Sentence": "review",
            "Aspect Term": "aspect",
            "polarity": "sentiment",
            "from": "start",
            "to": "end"
        }

        for name, path in self.paths.items():
            df = pd.read_csv(path)
            df = df.rename(columns=column_rename)
            print(f"{name} loaded. Shape: {df.shape}")
            print(df.head(), "\n")
            self.plot_sentiment_distribution(df, f"SemEval 2014 {name}")
            self.datasets[name] = df

        return self.datasets

    # Merge multiple datasets into one single dataset
    def merge_dataset(self):
        if not self.datasets:
            raise ValueError("No datasets loaded. Run load_dataset() first")

        self.combined_data = pd.concat(self.datasets.values(), ignore_index=True)
        self.plot_sentiment_distribution(self.combined_data, f"SemEval 2014 {' & '.join(self.paths.keys())}")
        return self.combined_data

    # Process the data by removing empty values and simplifying distribution
    def process(self):
        if self.combined_data is None:
            raise ValueError("No combined dataset found. Run merge_dataset() first")

        data = self.combined_data.copy()
        length_before = len(data)
        print(f"Length before dropping rows without aspects: {length_before}")

        # Dropping rows with missing aspects
        data = data.dropna(subset=["aspect"])
        length_after = len(data)

        final_length = length_before-length_after
        if final_length==0:
            print("There are no rows without an aspect.")
        else:
            print(f"Number of rows removed without aspect: {final_length}")

        data = data.reset_index(drop=True)
        print(f"Length after dropping rows without aspects: {len(data)}")
        print(data.head())
        print(data.tail())

        """
        For simpler sentiment distribution, the conflict class is removed.
        Turning the data into a 3-class distribution.
        """
        data = data[data["sentiment"] != "conflict"].reset_index(drop=True)
        print("\nRemoving the class 'conflict'...\nFinal Data: ")
        print(data.info())
        self.plot_sentiment_distribution(data, f"Final clean SemEval 2014 {' & '.join(self.paths.keys())}")

        self.final_data = data
        return self.final_data

    # Exporting file into csv
    def data_creation(self):
        if self.final_data is None:
            raise ValueError("No final dataset found. Run process() first")

        self.final_data.to_csv(FINAL_DATA, index=False)
        print(f"Dataset successfully exported to CSV at: {FINAL_DATA}")

# Main function
def main():
    # Define SemEval dataset configuration
    dataset_configs = {
        "Laptop": "SemEval_2014_dataset/Laptop_Train_v2.csv",
        "Restaurant": "SemEval_2014_dataset/Restaurants_Train_v2.csv"
    }

    # Initialize and run the SemEval data preprocesing pipeline
    SemPipeline = SemEvalPipeline(paths=dataset_configs)
    SemPipeline.load_dataset()
    SemPipeline.merge_dataset()

    # Get final dataset
    final_data = SemPipeline.process()
    SemPipeline.data_creation()
    return final_data


if __name__ == "__main__":
    clean_data = main()
    print(f"Final clean dataset shape: {len(clean_data)}")