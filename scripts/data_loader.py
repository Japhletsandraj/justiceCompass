
import kagglehub
from datasets import load_dataset
import os

# Create directory if it doesn't exist
os.makedirs("data/raw", exist_ok=True)

# Load the dataset directly from Hugging Face
ds = load_dataset("SnehaDeshmukh/IndianBailJudgments-1200")

# Convert the 'train' split to a pandas DataFrame and save to CSV
df = ds["train"].to_pandas()
df.to_csv("data/raw/indianbail_1200.csv", index=False)
# constitution of india dataset
path = kagglehub.dataset_download("rushikeshdarge/constitution-of-india")

print("Path to dataset files:", path)