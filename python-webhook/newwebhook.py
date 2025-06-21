import os
from flask import Flask, request
from kubernetes import client, config
import yaml
import time

app = Flask(__name__)


try:
    config.load_incluster_config()
except config.ConfigException:
    config.load_kube_config()

@app.route('/webhook', methods=['POST'])
def webhook_receiver():
    alert_data = request.json
    print(f"Received alert: {alert_data.get('commonAnnotations', {}).get('summary')}")

    if alert_data.get('commonLabels', {}).get('alertname') == 'MongoNightlyBackupFailed':
        print("MongoDB backup failure detected. Triggering immediate re-run Job.")
        rerun_backup_job()

    return "Webhook received", 200

def rerun_backup_job():
    api_client = client.ApiClient()
    current_time = int(time.time())
    job_name = f"mongo-backup-rerun-{current_time}" 
    dump_filename = f"mongodump-rerun-{current_time}.gz"
    job_yaml = """
apiVersion: batch/v1
kind: Job
metadata:
  name: {job_name}
spec:
  template:
    spec:
      containers:
      - name: mongodump-rerun-container
        image: mongo:5.0
        command:
        - /bin/sh
        - -c
        - |
          set -e
          
          echo "Installing dependencies for re-run..."
          apt-get update && apt-get install -y awscli

          # Variables are now passed in from Python
          S3_BUCKET="s3://mongodb-data-ups/ups"
          BACKUP_FILE="/tmp/{dump_filename}"

          echo "Starting immediate re-run mongodump to ${{BACKUP_FILE}}..."
          mongodump --uri="$MONGO_URI" --archive="${{BACKUP_FILE}}" --gzip
          
          echo "Re-run backup completed successfully. Uploading to S3..."
          aws s3 cp "${{BACKUP_FILE}}" "${{S3_BUCKET}}/{dump_filename}" 
          
          echo "Re-run upload to S3 successful."
        env:
        - name: MONGO_URI
          valueFrom:
            secretKeyRef:
              name: mongodb-secret
              key: mongo-uri
      restartPolicy: OnFailure
  backoffLimit: 2
"""
    
    unique_job_yaml = job_yaml.format(job_name=job_name, dump_filename=dump_filename)
    job_manifest = yaml.safe_load(unique_job_yaml)
    batch_v1_api = client.BatchV1Api(api_client)
    
    try:
        batch_v1_api.create_namespaced_job(body=job_manifest, namespace="default")
        print(f"Successfully created immediate re-run job: {job_manifest['metadata']['name']}")
    except client.ApiException as e:
        print(f"Error creating Kubernetes Job: {e}")