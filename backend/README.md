# GIS Pipeline Backend

FastAPI backend for the gas pipeline network visualization system.

## Setup

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Run the server:
```bash
python main.py
```

Or with uvicorn:
```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

## API Endpoints

- `GET /` - Health check
- `GET /api/flow/nodes?query_date=YYYY-MM-DD` - Node flow data
- `GET /api/flow/pipelines?query_date=YYYY-MM-DD` - Pipeline flow data
- `GET /api/flow/consumers?query_date=YYYY-MM-DD` - Consumer flow data
- `GET /api/flow/consumers/by-node?station_name=...&query_date=YYYY-MM-DD` - Consumers by station
- `GET /api/dates?data_type=node_flow|pipeline_flow|consumer_flow` - Available dates
- `GET /api/dates/range` - Date range summary

## Data Files

Place data in `backend/workspace/`:
- `node_flow/` - Node flow CSVs (`YYYYMMDD_node.csv`)
- `pipeline_flow/` - Pipeline flow CSVs (`YYYYMMDD_pipeline.csv`)
- `consumer_flow/` - Consumer flow CSVs (`YYYYMMDD_consumer.csv`)
- `consumer_station.csv` - Supply point to station mapping

## API Documentation

Once running, visit:
- http://localhost:8000/docs - Swagger UI
- http://localhost:8000/redoc - ReDoc
