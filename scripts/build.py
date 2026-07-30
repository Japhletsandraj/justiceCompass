#!/usr/bin/env python3
"""
build.py - Complete Knowledge Base Builder for JusticeCompass
This script downloads and processes all necessary datasets for the legal RAG system.
"""

import os
import json
import shutil
from pathlib import Path
from typing import Dict, List, Any, Optional
import sys

# ============================================================================
# DEPENDENCY CHECK & INSTALLATION
# ============================================================================

def check_and_install_dependencies():
    """Check and install required packages automatically."""
    required_packages = [
        "kagglehub",
        "huggingface-hub",
        "tqdm"
    ]
    
    missing = []
    for package in required_packages:
        try:
            __import__(package.replace("-", "_"))
        except ImportError:
            missing.append(package)
    
    if missing:
        print(f"📦 Installing missing dependencies: {', '.join(missing)}")
        import subprocess
        for package in missing:
            subprocess.check_call([sys.executable, "-m", "pip", "install", package])
        print("✅ All dependencies installed!")
        
        # Reload the modules after installation
        for package in missing:
            __import__(package.replace("-", "_"))

# Run dependency check
check_and_install_dependencies()

# Now import the required packages
import kagglehub
from huggingface_hub import hf_hub_download
from tqdm import tqdm

# ============================================================================
# CONFIGURATION
# ============================================================================

# Get the project root (where this script is located)
PROJECT_ROOT = Path(__file__).parent.absolute()
KB_ROOT = PROJECT_ROOT / "kb"

# Define all KB paths
PATHS = {
    "raw": KB_ROOT / "raw",
    "processed": KB_ROOT / "processed",
    "vector_db": KB_ROOT / "vector_db",
    "graph_db": KB_ROOT / "graph_db",
}

# Dataset definitions
# Dataset definitions - UPDATED WITH WORKING SOURCES
DATASETS = {
    "constitution": {
        "name": "Indian Constitution (Structured)",
        "source": "apurvthapa/indian-constitution-structured-dataset",
        "filename": "final.json",
        "raw_path": PATHS["raw"] / "constitution" / "final.json",
        "processed_path": PATHS["processed"] / "constitution_chunks.json",
        "type": "kaggle",
        "description": "Structured Constitution with article-level granularity and amendment tracking"
    },
    "case_law": {
        "name": "JITS Legal Case Law",
        "source": "nassimjp/jits-legal-dataset",
        "filename": "train.jsonl",
        "raw_path": PATHS["raw"] / "case_law" / "train.jsonl",
        "processed_path": PATHS["processed"] / "case_law_chunks.json",
        "type": "huggingface",
        "description": "Processed Indian judgments with citations and statutory references"
    },
    "statutes": {
        "name": "Indian Legal Texts (Statutes)",
        "source": "BharatGenAI/indian-legal-texts",  # Verified working source
        "filename": "legal_texts.json",
        "raw_path": PATHS["raw"] / "statutes" / "legal_texts.json",
        "processed_path": PATHS["processed"] / "statute_chunks.json",
        "type": "huggingface",
        "description": "Complete texts of Indian statutes (Contract Act, IT Act, etc.)"
    },
    "qa_pairs": {
        "name": "Indian Legal Q&A Pairs",
        "source": "law-ai/indian-legal-qa",  # Verified working source
        "filename": "qa_pairs.json",
        "raw_path": PATHS["raw"] / "qa_pairs" / "qa_pairs.json",
        "processed_path": PATHS["processed"] / "qa_pairs.json",
        "type": "huggingface",
        "description": "Question-Answer pairs for fine-tuning and RAG evaluation"
    }
}

# ============================================================================
# DIRECTORY SETUP
# ============================================================================

def setup_directories() -> None:
    """Create all necessary directories for the knowledge base."""
    print("\n📁 Creating directory structure...")
    
    for path in PATHS.values():
        path.mkdir(parents=True, exist_ok=True)
    
    # Create dataset-specific directories
    for dataset in DATASETS.values():
        dataset["raw_path"].parent.mkdir(parents=True, exist_ok=True)
        dataset["processed_path"].parent.mkdir(parents=True, exist_ok=True)
    
    print("✅ Directory structure created successfully")


# ============================================================================
# DOWNLOAD FUNCTIONS
# ============================================================================

def download_from_kaggle(dataset_config: Dict[str, Any]) -> Path:
    """Download a dataset from Kaggle."""
    print(f"  📥 Downloading from Kaggle: {dataset_config['source']}")
    
    try:
        download_path = kagglehub.dataset_download(dataset_config["source"])
        src_file = Path(download_path) / dataset_config["filename"]
        
        if not src_file.exists():
            raise FileNotFoundError(f"Expected file not found: {src_file}")
        
        shutil.copy2(src_file, dataset_config["raw_path"])
        print(f"  ✅ Saved to: {dataset_config['raw_path']}")
        
        return dataset_config["raw_path"]
    
    except Exception as e:
        print(f"  ❌ Error downloading {dataset_config['name']}: {e}")
        raise


def download_from_huggingface(dataset_config: Dict[str, Any]) -> Path:
    """Download a dataset from Hugging Face."""
    print(f"  📥 Downloading from Hugging Face: {dataset_config['source']}")
    
    try:
        downloaded_path = hf_hub_download(
            repo_id=dataset_config["source"],
            filename=dataset_config["filename"],
            repo_type="dataset",
            local_dir=str(dataset_config["raw_path"].parent),
        )
        
        print(f"  ✅ Saved to: {dataset_config['raw_path']}")
        return Path(downloaded_path)
    
    except Exception as e:
        print(f"  ❌ Error downloading {dataset_config['name']}: {e}")
        # Try alternative repo for statutes
        if dataset_config["source"] == "tejasgowda05/indian-legal-texts":
            print("  🔄 Trying alternative source for statutes...")
            try:
                alt_path = hf_hub_download(
                    repo_id="vivek-verma/indian-legal-texts",
                    filename=dataset_config["filename"],
                    repo_type="dataset",
                    local_dir=str(dataset_config["raw_path"].parent),
                )
                print(f"  ✅ Saved alternative to: {dataset_config['raw_path']}")
                return Path(alt_path)
            except Exception as e2:
                print(f"  ❌ Alternative also failed: {e2}")
                raise
        raise


def download_all_datasets() -> None:
    """Download all datasets."""
    print("\n" + "="*60)
    print("📥 STARTING DATASET DOWNLOAD")
    print("="*60)
    
    for key, config in DATASETS.items():
        print(f"\n📂 Processing: {config['name']}")
        print(f"   Description: {config['description']}")
        
        # Skip if already downloaded
        if config["raw_path"].exists():
            print(f"  ℹ️ Already exists at: {config['raw_path']}")
            continue
        
        try:
            if config["type"] == "kaggle":
                download_from_kaggle(config)
            elif config["type"] == "huggingface":
                download_from_huggingface(config)
            else:
                raise ValueError(f"Unknown dataset type: {config['type']}")
        except Exception as e:
            print(f"  ❌ Failed to download {config['name']}: {e}")
            print(f"  ℹ️ You can manually download and place it at: {config['raw_path']}")
    
    print("\n" + "="*60)
    print("✅ ALL DOWNLOADS COMPLETE")
    print("="*60)


# ============================================================================
# PROCESSING FUNCTIONS
# ============================================================================

def process_constitution(data: List[Dict]) -> List[Dict]:
    """Process constitution data for RAG."""
    print("  🔧 Processing constitution data...")
    
    processed = []
    for item in tqdm(data, desc="  Processing articles"):
        processed_item = {
            "id": item.get("article_number", ""),
            "text": item.get("content", ""),
            "type": item.get("document_type", "article"),
            "metadata": {
                "article_number": item.get("article_number", ""),
                "document_type": item.get("document_type", ""),
                "schedule_number": item.get("schedule_number"),
                "start_page": item.get("start_page"),
            }
        }
        # Add amendment notes if present
        if "amendment_notes" in item and item["amendment_notes"]:
            processed_item["metadata"]["amendments"] = item["amendment_notes"]
        
        processed.append(processed_item)
    
    return processed


def process_case_law(data: List[Dict]) -> List[Dict]:
    """Process case law data for RAG and Graph."""
    print("  🔧 Processing case law data...")
    
    processed = []
    for case in tqdm(data, desc="  Processing cases"):
        processed_case = {
            "id": case.get("id", ""),
            "text": case.get("text", ""),
            "metadata": {
                "court": case.get("court", ""),
                "date": case.get("date", ""),
                "case_number": case.get("case_number", ""),
                "judge": case.get("judge", []),
                "petitioner": case.get("petitioner", ""),
                "respondent": case.get("respondent", ""),
            }
        }
        
        # Extract citations for graph building
        if "citations" in case and case["citations"]:
            processed_case["citations"] = case["citations"]
        
        # Extract statutes referenced
        if "statutes_referenced" in case and case["statutes_referenced"]:
            processed_case["statutes"] = case["statutes_referenced"]
        
        # Add BNS mapping if available
        if "bns_mapping" in case and case["bns_mapping"]:
            processed_case["metadata"]["bns_mapping"] = case["bns_mapping"]
        
        processed.append(processed_case)
    
    return processed


def process_statutes(data: List[Dict]) -> List[Dict]:
    """Process statutes data for RAG."""
    print("  🔧 Processing statutes data...")
    
    processed = []
    for statute in tqdm(data, desc="  Processing statutes"):
        processed_statute = {
            "id": statute.get("act_name", ""),
            "text": statute.get("text", ""),
            "metadata": {
                "act_name": statute.get("act_name", ""),
                "act_year": statute.get("act_year", ""),
                "sections": statute.get("sections", []),
            }
        }
        processed.append(processed_statute)
    
    return processed


def process_qa_pairs(data: List[Dict]) -> List[Dict]:
    """Process QA pairs data."""
    print("  🔧 Processing QA pairs...")
    
    processed = []
    for qa in tqdm(data, desc="  Processing Q&A"):
        processed_qa = {
            "id": qa.get("id", ""),
            "question": qa.get("question", ""),
            "answer": qa.get("answer", ""),
            "metadata": {
                "context": qa.get("context", ""),
                "category": qa.get("category", ""),
                "source": qa.get("source", ""),
            }
        }
        processed.append(processed_qa)
    
    return processed


def process_all_datasets() -> None:
    """Process all downloaded datasets."""
    print("\n" + "="*60)
    print("⚙️ PROCESSING DATASETS")
    print("="*60)
    
    # Process Constitution
    print(f"\n📜 Processing: {DATASETS['constitution']['name']}")
    if DATASETS["constitution"]["raw_path"].exists():
        try:
            with open(DATASETS["constitution"]["raw_path"], 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            processed = process_constitution(data)
            
            with open(DATASETS["constitution"]["processed_path"], 'w', encoding='utf-8') as f:
                json.dump(processed, f, indent=2, ensure_ascii=False)
            
            print(f"  ✅ Processed {len(processed)} items")
            print(f"  💾 Saved to: {DATASETS['constitution']['processed_path']}")
        except Exception as e:
            print(f"  ❌ Error processing: {e}")
    else:
        print("  ⚠️ Raw data not found. Run download first.")
    
    # Process Case Law
    print(f"\n⚖️ Processing: {DATASETS['case_law']['name']}")
    if DATASETS["case_law"]["raw_path"].exists():
        try:
            data = []
            with open(DATASETS["case_law"]["raw_path"], 'r', encoding='utf-8') as f:
                for line in f:
                    data.append(json.loads(line))
            
            processed = process_case_law(data)
            
            with open(DATASETS["case_law"]["processed_path"], 'w', encoding='utf-8') as f:
                json.dump(processed, f, indent=2, ensure_ascii=False)
            
            print(f"  ✅ Processed {len(processed)} items")
            print(f"  💾 Saved to: {DATASETS['case_law']['processed_path']}")
        except Exception as e:
            print(f"  ❌ Error processing: {e}")
    else:
        print("  ⚠️ Raw data not found. Run download first.")
    
    # Process Statutes
    print(f"\n📚 Processing: {DATASETS['statutes']['name']}")
    if DATASETS["statutes"]["raw_path"].exists():
        try:
            with open(DATASETS["statutes"]["raw_path"], 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            processed = process_statutes(data)
            
            with open(DATASETS["statutes"]["processed_path"], 'w', encoding='utf-8') as f:
                json.dump(processed, f, indent=2, ensure_ascii=False)
            
            print(f"  ✅ Processed {len(processed)} items")
            print(f"  💾 Saved to: {DATASETS['statutes']['processed_path']}")
        except Exception as e:
            print(f"  ❌ Error processing: {e}")
    else:
        print("  ⚠️ Raw data not found. Run download first.")
    
    # Process QA Pairs
    print(f"\n❓ Processing: {DATASETS['qa_pairs']['name']}")
    if DATASETS["qa_pairs"]["raw_path"].exists():
        try:
            with open(DATASETS["qa_pairs"]["raw_path"], 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            processed = process_qa_pairs(data)
            
            with open(DATASETS["qa_pairs"]["processed_path"], 'w', encoding='utf-8') as f:
                json.dump(processed, f, indent=2, ensure_ascii=False)
            
            print(f"  ✅ Processed {len(processed)} items")
            print(f"  💾 Saved to: {DATASETS['qa_pairs']['processed_path']}")
        except Exception as e:
            print(f"  ❌ Error processing: {e}")
    else:
        print("  ⚠️ Raw data not found. Run download first.")
    
    print("\n" + "="*60)
    print("✅ ALL PROCESSING COMPLETE")
    print("="*60)


# ============================================================================
# LOAD FUNCTIONS (for use in your main application)
# ============================================================================

def load_constitution() -> List[Dict]:
    """Load processed constitution data."""
    path = DATASETS["constitution"]["processed_path"]
    if not path.exists():
        raise FileNotFoundError(f"Constitution data not found at {path}. Run build first.")
    
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def load_case_law(limit: Optional[int] = None) -> List[Dict]:
    """Load processed case law data."""
    path = DATASETS["case_law"]["processed_path"]
    if not path.exists():
        raise FileNotFoundError(f"Case law data not found at {path}. Run build first.")
    
    with open(path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    return data[:limit] if limit else data


def load_statutes() -> List[Dict]:
    """Load processed statutes data."""
    path = DATASETS["statutes"]["processed_path"]
    if not path.exists():
        raise FileNotFoundError(f"Statutes data not found at {path}. Run build first.")
    
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def load_qa_pairs() -> List[Dict]:
    """Load processed QA pairs data."""
    path = DATASETS["qa_pairs"]["processed_path"]
    if not path.exists():
        raise FileNotFoundError(f"QA pairs data not found at {path}. Run build first.")
    
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def load_all_data() -> Dict[str, List[Dict]]:
    """Load all processed data."""
    print("\n📚 Loading all KB data...")
    
    data = {
        "constitution": load_constitution(),
        "case_law": load_case_law(),
        "statutes": load_statutes(),
        "qa_pairs": load_qa_pairs(),
    }
    
    print(f"  ✅ Constitution: {len(data['constitution'])} items")
    print(f"  ✅ Case Law: {len(data['case_law'])} items")
    print(f"  ✅ Statutes: {len(data['statutes'])} items")
    print(f"  ✅ QA Pairs: {len(data['qa_pairs'])} items")
    
    return data


# ============================================================================
# STATISTICS & INFO
# ============================================================================

def show_stats() -> None:
    """Display statistics about the knowledge base."""
    print("\n" + "="*60)
    print("📊 KNOWLEDGE BASE STATISTICS")
    print("="*60)
    
    for key, config in DATASETS.items():
        print(f"\n📂 {config['name']}")
        print(f"   Description: {config['description']}")
        
        if config["raw_path"].exists():
            size = config["raw_path"].stat().st_size / (1024 * 1024)  # MB
            print(f"   Raw file size: {size:.2f} MB")
        else:
            print("   Raw file: ❌ Not found")
        
        if config["processed_path"].exists():
            try:
                with open(config["processed_path"], 'r', encoding='utf-8') as f:
                    data = json.load(f)
                print(f"   Processed items: {len(data)}")
            except:
                print("   Processed items: ❌ Error reading")
        else:
            print("   Processed file: ❌ Not found")


# ============================================================================
# MAIN ENTRY POINT
# ============================================================================

def main():
    """Main entry point for the Knowledge Base builder."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="JusticeCompass Knowledge Base Builder",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python build.py --all          # Download and process everything
  python build.py --download     # Only download datasets
  python build.py --process      # Only process datasets
  python build.py --stats        # Show KB statistics
  python build.py --load         # Test loading all data
        """
    )
    
    parser.add_argument("--all", action="store_true", help="Download and process all datasets")
    parser.add_argument("--download", action="store_true", help="Only download datasets")
    parser.add_argument("--process", action="store_true", help="Only process datasets")
    parser.add_argument("--stats", action="store_true", help="Show KB statistics")
    parser.add_argument("--load", action="store_true", help="Test loading all data")
    parser.add_argument("--setup", action="store_true", help="Only create directory structure")
    
    args = parser.parse_args()
    
    # If no arguments, show help
    if len(sys.argv) == 1:
        parser.print_help()
        sys.exit(0)
    
    # Setup directories
    setup_directories()
    
    # Execute based on arguments
    if args.all:
        download_all_datasets()
        process_all_datasets()
        show_stats()
    
    elif args.download:
        download_all_datasets()
    
    elif args.process:
        process_all_datasets()
    
    elif args.stats:
        show_stats()
    
    elif args.load:
        print("\n🧪 Testing data loading...")
        try:
            data = load_all_data()
            print("\n✅ All data loaded successfully!")
            print(f"   Total items: {sum(len(v) for v in data.values())}")
        except Exception as e:
            print(f"❌ Error loading data: {e}")
    
    elif args.setup:
        print("✅ Directory structure created.")
    
    else:
        parser.print_help()
    
    print("\n" + "="*60)
    print("🏛️ JusticeCompass Knowledge Base Ready!")
    print("="*60)
    

if __name__ == "__main__":
    main()