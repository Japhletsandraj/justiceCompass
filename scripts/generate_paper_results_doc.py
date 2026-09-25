from pathlib import Path

from docx import Document
from docx.shared import Inches
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "paper_artifacts"
OUT_DIR.mkdir(exist_ok=True)

RESULTS = {
    "tests_passed": 8,
    "test_runtime_sec": 75.41,
    "statute_docs": 21,
    "statute_sections": 3282,
    "case_law_records": 1392,
    "crossref_entries": 270,
    "vector_db_records": 5452,
    "citation_coverage_pct": 94.7,
    "unmapped_ipc_sections": 90,
    "domain_coverage": {
        "constitutional_law": {"statutes": 1, "sections": 454, "case_law": 0},
        "criminal_law": {"statutes": 5, "sections": 2159, "case_law": 1200},
        "consumer_protection": {"statutes": 2, "sections": 142, "case_law": 0},
        "family_law": {"statutes": 3, "sections": 130, "case_law": 0},
        "tenancy_property": {"statutes": 10, "sections": 397, "case_law": 0},
    },
}


def save_corpus_chart():
    labels = ["Statute docs", "Statute sections", "Case law", "Cross-ref", "Vector records"]
    values = [
        RESULTS["statute_docs"],
        RESULTS["statute_sections"],
        RESULTS["case_law_records"],
        RESULTS["crossref_entries"],
        RESULTS["vector_db_records"],
    ]
    fig, ax = plt.subplots(figsize=(7, 4))
    ax.bar(labels, values, color=["#2f6fed", "#5aa9e6", "#7dd3fc", "#fbbf24", "#34d399"])
    ax.set_ylabel("Count")
    ax.set_title("JusticeCompass corpus composition")
    for i, v in enumerate(values):
        ax.text(i, v + 0.02 * max(values), f"{v:,}", ha="center", va="bottom", fontsize=8)
    plt.xticks(rotation=15)
    fig.tight_layout()
    fig.savefig(OUT_DIR / "corpus_composition.png", dpi=200, bbox_inches="tight")
    plt.close(fig)


def save_domain_chart():
    domains = list(RESULTS["domain_coverage"].keys())
    case_law = [RESULTS["domain_coverage"][d]["case_law"] for d in domains]
    statutes = [RESULTS["domain_coverage"][d]["statutes"] for d in domains]

    fig, axes = plt.subplots(1, 2, figsize=(12, 4.8), sharey=True)
    x = range(len(domains))

    axes[0].bar(x, statutes, color="#fbbf24", alpha=0.9)
    axes[0].set_xticks(list(x))
    axes[0].set_xticklabels(domains, rotation=20, ha="right")
    axes[0].set_ylabel("Statute documents")
    axes[0].set_title("Statute coverage by domain")
    axes[0].set_ylim(0, 14)
    for i, v in enumerate(statutes):
        axes[0].text(i, v + 0.25, str(v), ha="center", va="bottom", fontsize=8)

    axes[1].bar(x, case_law, color="#2563eb", alpha=0.9)
    axes[1].set_xticks(list(x))
    axes[1].set_xticklabels(domains, rotation=20, ha="right")
    axes[1].set_ylabel("Case-law records")
    axes[1].set_title("Case-law coverage by domain")
    axes[1].set_ylim(0, 1300)
    for i, v in enumerate(case_law):
        if v > 0:
            axes[1].text(i, v + 25, str(v), ha="center", va="bottom", fontsize=8)

    fig.suptitle("Coverage by legal domain", y=1.02)
    fig.tight_layout()
    fig.savefig(OUT_DIR / "domain_coverage.png", dpi=200, bbox_inches="tight")
    plt.close(fig)


def write_markdown():
    md = f'''# JusticeCompass Results Summary

## Verified implementation results

- Repository test suite: {RESULTS['tests_passed']} tests passed
- Total runtime: {RESULTS['test_runtime_sec']}s
- System behavior: abstains with `insufficient_data` for small comparable cohorts

## Corpus and coverage

- Statute documents: {RESULTS['statute_docs']:,}
- Statute sections: {RESULTS['statute_sections']:,}
- Case-law records: {RESULTS['case_law_records']:,}
- Cross-reference entries: {RESULTS['crossref_entries']:,}
- Vector database records: {RESULTS['vector_db_records']:,}
- Citation coverage: {RESULTS['citation_coverage_pct']:.1f}%
- Unmapped IPC sections still requiring manual completion: {RESULTS['unmapped_ipc_sections']:,}

## Domain profile

| Domain | Statutes | Sections | Case law |
|---|---:|---:|---:|
| constitutional_law | 1 | 454 | 0 |
| criminal_law | 5 | 2,159 | 1,200 |
| consumer_protection | 2 | 142 | 0 |
| family_law | 3 | 130 | 0 |
| tenancy_property | 10 | 397 | 0 |

## Paper-ready paragraph

> JusticeCompass was validated on the current implementation with 8 automated tests passing successfully. The project knowledge base contains 21 statute documents, 3,282 statute sections, 1,392 case-law records, 270 cross-reference entries, and 5,452 vector database records. Coverage is strongest in criminal law, where 1,200 bail-related judgments are available; other domains are represented primarily by statutes rather than case law. The system reports 94.7% citation coverage in the cross-reference layer, while noting that 90 IPC sections remain unmapped and that the concordance is not yet verified against an official government mapping. The model abstains with `insufficient_data` when comparable outcome data are too small, avoiding unsupported probability estimates. A full held-out retrieval and answer-quality benchmark has not yet been executed in the repository, so these results reflect implementation validation and corpus coverage rather than final benchmarked retrieval metrics.

## Short wording for a table

| Component | Evaluation unit | Verified result |
|---|---|---|
| System validation | Repository pipeline | 8 tests passed; runtime 75.41s |
| Corpus coverage | Knowledge base | 21 statute docs; 3,282 sections; 1,392 case-law records; 270 cross-ref entries |
| Citation coverage | Cross-reference layer | 94.7% |
| Outcome safety | Abstention logic | `insufficient_data` when comparable sample is too small |
| Benchmark status | Held-out evaluation | Not yet executed; final retrieval/answer metrics remain pending |
'''
    (OUT_DIR / "justicecompass_results.md").write_text(md, encoding="utf-8")


def write_txt_summary():
    text = '''JusticeCompass paper-ready summary

Validated implementation:
- 8 tests passed
- 75.41 seconds total runtime
- Abstains with insufficient_data when comparable case data are too small

Corpus data:
- 21 statute documents
- 3,282 statute sections
- 1,392 case-law records
- 270 cross-reference entries
- 5,452 vector database records
- Citation coverage: 94.7%
- 90 IPC sections remain manually unmapped

Coverage profile:
- criminal_law: 5 statute docs, 2,159 sections, 1,200 case-law records
- constitutional_law: 1 statute doc, 454 sections, 0 case-law records
- consumer_protection: 2 statute docs, 142 sections, 0 case-law records
- family_law: 3 statute docs, 130 sections, 0 case-law records
- tenancy_property: 10 statute docs, 397 sections, 0 case-law records

Paper-ready paragraph:
JusticeCompass was validated on the current implementation with 8 automated tests passing successfully. The project knowledge base contains 21 statute documents, 3,282 statute sections, 1,392 case-law records, 270 cross-reference entries, and 5,452 vector database records. Coverage is strongest in criminal law, where 1,200 bail-related judgments are available; other domains are represented primarily by statutes rather than case law. The system reports 94.7% citation coverage in the cross-reference layer, while noting that 90 IPC sections remain unmapped and that the concordance is not yet verified against an official government mapping. The model abstains with insufficient_data when comparable outcome data are too small, avoiding unsupported probability estimates. A full held-out retrieval and answer-quality benchmark has not yet been executed in the repository, so these results reflect implementation validation and corpus coverage rather than final benchmarked retrieval metrics.
'''
    (OUT_DIR / "justicecompass_results.txt").write_text(text, encoding="utf-8")


def build_docx():
    doc = Document()
    doc.add_heading("JusticeCompass Results for the Paper", 0)

    doc.add_paragraph(
        "This section reports only repository-backed, verified results. No final held-out retrieval benchmark was executed in the current codebase, so the values below remain implementation and coverage results rather than publication-ready benchmark metrics."
    )

    table = doc.add_table(rows=1, cols=3)
    table.style = "Table Grid"
    headers = ["Component", "Evaluation unit", "Verified result"]
    for i, h in enumerate(headers):
        table.rows[0].cells[i].text = h

    rows = [
        ["System validation", "Repository pipeline", "8 tests passed; 75.41s total runtime"],
        ["Corpus coverage", "Knowledge base", "21 statute docs; 3,282 sections; 1,392 case-law records; 270 cross-ref entries; 5,452 vector records"],
        ["Citation quality", "Cross-reference layer", "94.7% citation coverage; 90 IPC sections require manual mapping"],
        ["Outcome safety", "Abstention logic", "Returns insufficient_data when comparable cohort is too small"],
        ["Benchmark status", "Held-out evaluation", "Not yet executed; final retrieval and answer-quality metrics remain pending"],
    ]
    for r in rows:
        row = table.add_row().cells
        for i, v in enumerate(r):
            row[i].text = v

    doc.add_paragraph("\nPaper-ready paragraph:")
    para = doc.add_paragraph()
    para.add_run(
        "JusticeCompass was validated on the current implementation with 8 automated tests passing successfully. The project knowledge base contains 21 statute documents, 3,282 statute sections, 1,392 case-law records, 270 cross-reference entries, and 5,452 vector database records. Coverage is strongest in criminal law, where 1,200 bail-related judgments are available; other domains are represented primarily by statutes rather than case law. The system reports 94.7% citation coverage in the cross-reference layer, while noting that 90 IPC sections remain unmapped and that the concordance is not yet verified against an official government mapping. The model abstains with insufficient_data when comparable outcome data are too small, avoiding unsupported probability estimates. A full held-out retrieval and answer-quality benchmark has not yet been executed in the repository, so these results reflect implementation validation and corpus coverage rather than final benchmarked retrieval metrics."
    )

    doc.add_paragraph("Corpus composition")
    doc.add_picture(str(OUT_DIR / "corpus_composition.png"), width=Inches(5.4))

    doc.add_paragraph("Coverage by legal domain")
    doc.add_picture(str(OUT_DIR / "domain_coverage.png"), width=Inches(5.8))

    doc.save(OUT_DIR / "justicecompass_results.docx")


if __name__ == "__main__":
    save_corpus_chart()
    save_domain_chart()
    write_markdown()
    write_txt_summary()
    build_docx()
    print(f"Saved outputs to: {OUT_DIR}")
