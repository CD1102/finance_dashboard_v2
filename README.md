# Finance Dashboard

A personal financial command centre designed to answer:

> **How am I doing, and where am I heading?**

The application tracks monthly financial snapshots and account balances rather than individual transactions. It provides a single place to understand current net worth, financial progress, goals and projections.

## Features

- Current net worth and account balances
- Cash, investments and pension breakdown
- Monthly income, spending and contributions
- Historical financial records
- Net worth and financial performance over time
- Savings rate and cash-flow analysis
- Financial goals and progress tracking
- Future projections and scenarios
- UK tax calculations and financial insights
- Spreadsheet import
- Data export, backup and restore
- Synthetic sample data for development
- Automated test coverage

## Running locally

Create and activate a virtual environment:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
```

Install the development dependencies:

```powershell
python -m pip install -r requirements-dev.txt
```

Run the application:

```powershell
streamlit run app.py
```

## Running with Docker

Build and start the application with Docker Compose:

```powershell
docker compose up --build
```

The application will be available at:

```text
http://localhost:8501
```

Docker Compose mounts a persistent volume at `/data` so application data survives container restarts.

## Architecture

The application is deliberately separated into a small number of layers.

```text
app.py
  │
  ▼
views/
  │
  ▼
financelib/
  ├── calculations/
  ├── models.py
  ├── storage/
  ├── importers/
  ├── formatting/
  └── ui/
```

`app.py` handles navigation.

`views/` contains the individual application screens and keeps Streamlit-specific code relatively thin.

`financelib/` contains the core application logic, including financial calculations, data models, storage, formatting and UI components.

The calculation layer does not depend on Streamlit or direct file access.

### Data model

Financial information is stored as monthly records.

Example:

```json
{
  "month": "2026-09",
  "income": 3478.00,
  "spending": 2383.00,
  "spending_categories": {
    "Housing": 780.00,
    "Food & groceries": 390.00
  },
  "contributions": {
    "stocks_isa": 450.00,
    "cash_isa": 300.00
  },
  "balances": {
    "stocks_isa": 34487.12,
    "cash_isa": 18312.40
  }
}
```

Fields are optional. A blank value means that information was not recorded rather than assuming it was zero.

The application distinguishes between:

- **Recorded** — directly entered financial information
- **Calculated** — values derived from recorded information
- **Projected** — estimates of future financial outcomes

The application deliberately avoids guessing missing financial information. For example, missing contribution data prevents the application from incorrectly presenting investment growth as purely market performance.

## Storage

Storage is accessed through a repository abstraction defined in:

```text
financelib/storage/base.py
```

The current implementation uses JSON files through `JsonRepository`.

The storage location can be changed using:

```text
FINANCE_DATA_DIR
```

This allows the same application to use different storage locations in local development, Docker and Azure.

The storage layer uses atomic writes and backups to reduce the risk of corrupting financial data.

The architecture allows a future SQLite or PostgreSQL implementation to be introduced without changing the calculation or view layers.

## Data safety

Real financial data should never be committed to Git.

The repository excludes personal data under `data/` while allowing synthetic sample data under:

```text
data/samples/
```

Synthetic data can be generated with:

```powershell
python tools/make_samples.py
```

The application also provides data export, backup and restore functionality.

## Cloud deployment

The application is deployed to Microsoft Azure as a containerised application.

```text
GitHub
   │
   ▼
GitHub Actions
   ├── Run pytest
   ├── Build Docker image
   ├── Push image to Azure Container Registry
   └── Deploy infrastructure with Bicep
              │
              ▼
      Azure Container Apps
              │
        ┌─────┴─────┐
        ▼           ▼
   Docker image   Azure Files
      (ACR)       (/data)
                    │
                    ▼
             Persistent JSON data
```

### Azure infrastructure

Infrastructure is defined using Bicep:

```text
infra/
├── main.bicep
└── resources.bicep
```

`main.bicep` operates at subscription scope and creates the resource group.

`resources.bicep` operates within the resource group and defines the application resources.

The deployment manages:

- Azure Resource Group
- Azure Container Registry
- Azure Container Apps Environment
- Azure Container App
- User-assigned managed identities
- Azure Storage Account
- Azure Files share
- Container App storage mount
- Required RBAC assignments

### CI/CD

GitHub Actions runs automatically for pushes to `main` and pull requests targeting `main`.

The deployment pipeline:

1. Checks out the repository.
2. Installs Python 3.12.
3. Installs development dependencies.
4. Runs the test suite.
5. Builds the Docker image.
6. Authenticates to Azure using GitHub OIDC.
7. Pushes the Docker image to Azure Container Registry.
8. Deploys the Azure infrastructure using Bicep.

The Docker image is tagged using the Git commit SHA so that each deployment can be associated with a specific version of the source code.

### Authentication

GitHub Actions authenticates to Azure using OpenID Connect (OIDC).

No long-lived Azure client secret is stored in GitHub.

The workflow uses a user-assigned managed identity with a federated credential that trusts the appropriate GitHub repository and branch.

The identity has permissions required by the deployment pipeline, including:

- Contributor
- Role Based Access Control Administrator
- AcrPush

The ACR push permission is scoped specifically to the application's Azure Container Registry.

### Persistent storage

Container filesystems are ephemeral. Data stored only inside a container can be lost when the container is restarted or replaced.

The application therefore mounts an Azure Files share at:

```text
/data
```

The application continues to use the same `FINANCE_DATA_DIR` configuration as it does locally.

In Azure:

```text
Container App
     │
     │ /data
     ▼
Azure Files
     │
     ▼
Persistent application data
```

This means financial records survive container restarts and redeployments.

Persistence has been tested by restarting the running Container App and verifying that previously stored account data remained available.

### Scaling

The Container App is configured with:

```text
Minimum replicas: 0
Maximum replicas: 1
```

This allows the application to scale to zero when it is not being used, reducing unnecessary compute usage.

When traffic returns, Azure can start a new container and mount the same persistent Azure Files storage.

## Monitoring

Container logs can be inspected through Azure CLI:

```powershell
az containerapp logs show `
  --name finance-dashboard `
  --resource-group finance-dashboard-rg `
  --tail 50
```

The Container App revision and replica health can also be inspected through Azure CLI.

## Cost management

The project uses Azure Cost Management with a monthly budget of:

```text
£5
```

Alerts are configured at:

- £4 — 80%
- £5 — 100%

The application also uses Container Apps scale-to-zero to reduce unnecessary compute costs.

## Testing

The project includes a comprehensive automated test suite covering financial calculations, edge cases, storage behaviour and application smoke tests.

Run the tests with:

```powershell
pytest
```

The current test suite contains **273 tests**.

GitHub Actions runs the same test suite before a Docker image is deployed.

## Project structure

```text
finance_dashboard_v2/
│
├── .github/
│   └── workflows/
│       └── ci.yml
│
├── .streamlit/
│
├── data/
│
├── financelib/
│   ├── calculations/
│   ├── formatting/
│   ├── importers/
│   ├── storage/
│   ├── ui/
│   └── models.py
│
├── infra/
│   ├── main.bicep
│   └── resources.bicep
│
├── tests/
│
├── tools/
│
├── views/
│
├── .dockerignore
├── .gitignore
├── app.py
├── compose.yaml
├── Dockerfile
├── pytest.ini
├── README.md
├── requirements.txt
└── requirements-dev.txt
```

## Current limitations

- UK tax calculations use whole-month approximations.
- Investment performance is approximated using starting balances and average contribution timing.
- Future projections use constant assumed growth rates.
- The application is currently designed for a single user.
- Financial data is intentionally based on monthly snapshots rather than transaction-level data.

## Future storage options

The storage abstraction allows the JSON implementation to be replaced with another repository implementation in the future.

Potential options include:

- SQLite for a simple persistent relational database
- PostgreSQL for a larger multi-user implementation

These are intentionally not required for the current application.

## Project status

The application is deployed and operational on Azure.

The current platform demonstrates:

- Python application development
- Automated testing
- Git and GitHub
- Docker containerisation
- GitHub Actions CI/CD
- Azure Container Registry
- Azure Container Apps
- Infrastructure as Code with Bicep
- GitHub OIDC authentication
- Managed identities
- Azure RBAC
- Persistent Azure Files storage
- Application logging
- Azure cost management

## Deployment status

Deployed to Azure using automated GitHub Actions CI/CD.