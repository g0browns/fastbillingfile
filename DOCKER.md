# Docker Run Guide

## 1) Prerequisites
- Install Docker Desktop
- Ensure your `.env` file exists in the project root

## 2) Build and start
```powershell
docker compose up --build -d
```

## 3) Open app
- [http://localhost:8000](http://localhost:8000)

## 4) Stop app
```powershell
docker compose down
```

## 5) View logs
```powershell
docker compose logs -f
```

## Notes
- Container exposes app on internal port `8001`, mapped to host `8000`.
- `./output` is mounted so generated files remain on your machine.
