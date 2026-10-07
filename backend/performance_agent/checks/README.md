# Performance Analyzer checks

These are manual verification scripts, not automated tests. Each one loads a
CSV and prints what it finds, so they are slow and have side effects. They were
previously named `test_*.py`, which made pytest try to collect them.

They are not collected today because `pyproject.toml` sets
`testpaths = ["tests"]`, pointing at the backend suite only. That is a
coincidence of configuration, not a safeguard, and it is why they were renamed.

Run one directly:

```bash
cd backend
python -m performance_agent.checks.check_loader
```

Every script reads from `performance_agent/data/`, which is gitignored. Run
`python -m performance_agent.create_sample_dataset` first to generate
`Financials_standardized.csv` from `Financials.csv`.

| Script | Analyzer exercised |
|---|---|
| `check_loader.py` | `DataLoader` column cleaning |
| `check_schema.py` | `SchemaDetector` |
| `check_company_analysis.py` | `CompanyAnalyzer` |
| `check_employee_analysis.py` | `EmployeeAnalyzer` |
| `check_department_analysis.py` | `DepartmentAnalyzer` |
| `check_product_analysis.py` | `ProductAnalyzer` |
| `check_regional_analysis.py` | `RegionalAnalyzer` |
| `check_customer_analysis.py` | `CustomerAnalyzer` |
| `check_channel_analysis.py` | `ChannelAnalyzer` |
| `check_target_analysis.py` | `TargetAnalyzer` |
| `check_time_analysis.py` | `TimeAnalyzer` |

These analyzers are not wired to the API. The Performance Analyzer is deferred
until its batch-job shape is settled.

Real automated coverage lives in `backend/tests/`, using fakes only.