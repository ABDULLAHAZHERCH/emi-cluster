# DS-584: Cloud Computing — Assignment 4
**Deploying, Load Balancing, and Autoscaling a Loan EMI Calculator with MongoDB on Kubernetes (Minikube)**

## Overview
This project implements a containerized Loan EMI Calculator web application backed by a 3-member MongoDB replica set (`rs0`) and deployed on a single-node Minikube Kubernetes cluster. External HTTP traffic enters through the NGINX Ingress controller (`http://emi.local`), load-balances across `emi-web` pods behind a ClusterIP Service, persists calculations to MongoDB PersistentVolumes, and dynamically scales pod replicas using a Horizontal Pod Autoscaler (HPA).

---

## Repository Structure
```text
.
├── app/
│   ├── app.py                # Flask REST API (/api/emi, /api/history, /health) & PyMongo client
│   ├── templates/
│   │   └── index.html        # Bootstrap 5 + jQuery AJAX frontend (no postback)
│   ├── requirements.txt      # Python dependencies (Flask, PyMongo, Gunicorn)
│   ├── Dockerfile            # Slim non-root container image definition
│   └── .dockerignore         # Excludes virtual environments, caches, and Git metadata
├── k8s/
│   ├── 00-namespace.yaml         # Namespace: emi
│   ├── 01-mongo-service.yaml     # Headless Service (clusterIP: None) for StatefulSet DNS
│   ├── 02-mongo-statefulset.yaml # 3-replica MongoDB StatefulSet (--replSet rs0) with 1Gi PVCs
│   ├── 03-mongo-init-job.yaml    # Kubernetes Job initiating replica set rs0
│   ├── 04-configmap.yaml         # ConfigMap storing MONGO_URL connection string
│   ├── 05-web-deployment.yaml    # emi-web Deployment (probes + 100m/128Mi requests, 250m/256Mi limits)
│   ├── 06-web-service.yaml       # ClusterIP Service exposing emi-web on port 80
│   ├── 07-ingress.yaml           # NGINX Ingress routing emi.local -> emi-web:80
│   └── 08-hpa.yaml               # HorizontalPodAutoscaler (1–5 replicas @ 50% CPU utilization)
├── scripts/
│   ├── test_load_distribution.py # Sends 30 POST /api/emi requests and tallies servedBy pods
│   ├── rollout_traffic_loop.py   # Continuous request loop verifying zero-downtime rolling updates
│   ├── run_fixed_experiments.py  # Runs 15 httperf benchmarks (1, 2, 3 replicas x 10–200 req/s)
│   ├── run_hpa_test.py           # Runs 10-minute autoscaling workload and polls HPA every 15s
│   └── plot_results.py           # Generates Milestone 04 evaluation graphs from CSV outputs
├── results/                      # Raw httperf outputs, CPU/pod/HPA profiling CSVs, and PNG graphs
└── README.md
```

---

## Prerequisites
* **Host Tools:** Docker, Minikube, `kubectl`, Python 3 (`psutil`, `pandas`, `matplotlib`), and `httperf`
* **Cluster Addons:** NGINX Ingress Controller (`ingress`) and Metrics Server (`metrics-server`)

---

## Deploying on a Fresh Minikube Cluster

### 1. Start Minikube and Enable Addons
```bash
minikube start
minikube addons enable ingress
minikube addons enable metrics-server
```

### 2. Build the Web Application Image and Load into Minikube
```bash
docker build -t emi-web:1.0 ./app
minikube image load emi-web:1.0
```
*(Optional: Pre-load `mongo:7` with `docker pull mongo:7 && minikube image load mongo:7` to speed up StatefulSet startup.)*

### 3. Apply All Kubernetes Manifests
Deploy the namespace, MongoDB replica set, initialization Job, ConfigMap, web Deployment/Service, Ingress, and HPA in a single command:
```bash
kubectl apply -f k8s/
```

### 4. Verify Cluster Readiness
Wait until all MongoDB pods (`mongo-0`, `mongo-1`, `mongo-2`) and `emi-web` pods reach `1/1 Running`, and `mongo-init` reaches `Completed`:
```bash
kubectl get all,pvc,configmap -n emi -o wide
```
Confirm replica set `rs0` has one `PRIMARY` and two `SECONDARY` members:
```bash
kubectl logs job/mongo-init -n emi
kubectl exec -it mongo-0 -n emi -- mongosh --quiet --eval "rs.status().members.map(m => ({name: m.name, state: m.stateStr}))"
```

### 5. Configure Local Hostname (`emi.local`)
* **Linux:**
  ```bash
  sudo sed -i '/emi\.local/d' /etc/hosts
  echo "$(minikube ip) emi.local" | sudo tee -a /etc/hosts
  ```
* **Windows / macOS (Docker driver):**
  Run `minikube tunnel` in a separate terminal and add `127.0.0.1 emi.local` to your hosts file.

Open `http://emi.local` in your browser to use the Loan EMI Calculator.

---

## Running Verification & Benchmarking Scripts

### Milestone 03: Load Distribution & Rolling Update
* **Test request distribution across pods:**
  ```bash
  python3 scripts/test_load_distribution.py
  ```
* **Zero-downtime rolling update (`1.0` -> `1.1`) and rollback:**
  ```bash
  # Terminal 1
  python3 scripts/rollout_traffic_loop.py

  # Terminal 2
  docker build -t emi-web:1.1 ./app
  minikube image load emi-web:1.1
  kubectl set image deployment/emi-web emi-web=emi-web:1.1 -n emi
  kubectl rollout status deployment/emi-web -n emi
  kubectl rollout undo deployment/emi-web -n emi
  ```

### Milestone 04: Load Testing, Profiling & Autoscaling
* **Fixed-replica benchmarks (remove HPA first so replica counts stay fixed at 1, 2, and 3):**
  ```bash
  kubectl delete hpa emi-web -n emi --ignore-not-found
  python3 scripts/run_fixed_experiments.py
  kubectl apply -f k8s/08-hpa.yaml
  ```
* **10-minute HPA autoscaling test (`10 req/s` -> `100 req/s` -> `10 req/s`):**
  ```bash
  python3 scripts/run_hpa_test.py
  ```
* **Generate evaluation graphs in `results/`:**
  ```bash
  python3 scripts/plot_results.py
  ```

---

## Cleanup
To remove all assignment resources from the cluster:
```bash
kubectl delete namespace emi
```
