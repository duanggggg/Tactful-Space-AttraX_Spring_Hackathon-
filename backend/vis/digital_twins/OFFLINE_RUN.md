# Offline Run Guide

## Contents

- `start_backend.sh`: start the FastAPI mock backend
- `start_frontend.sh`: start the Vite frontend
- `start_all.sh`: start backend first, then frontend
- `prepare_backend_venv.sh`: create the backend virtual environment on an online machine
- `package_offline_bundle.sh`: build a portable `.tar.gz` bundle

## Before Packaging

Run these on the online machine:

```bash
cd backend/vis/digital_twins
./prepare_backend_venv.sh
cd frontend
npm install
cd ..
./package_offline_bundle.sh
```

## On the Offline Machine

Extract the bundle, then run:

```bash
cd backend/vis/digital_twins
./start_all.sh
```

If you prefer separate terminals:

```bash
./start_backend.sh
```

and:

```bash
./start_frontend.sh
```

## Default URLs

- Backend: `http://127.0.0.1:8787`
- Frontend: `http://127.0.0.1:5173`
