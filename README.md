# Connecting your Prometheus alerts to an API-based ITSM tool / Servicenow

```
git clone https://github.com/imsanjeevi/prom-snow -b python
```

## Python version
```sh
cd prom-snow
# cp .env.example .env
pip install -r requirements.txt
python run app/main.py
```

## Docker
```sh
cd prom-snow
docker build -t msanjeevi/prom-snow-webhook .
docker build -t msanjeevi/prom-snow-webhook --platform linux/amd64 .

# https://docs.docker.com/go/build-multi-platform/
docker build -t msanjeevi/prom-snow-webhook --platform linux/amd64,linux/arm64 .

docker buildx build --platform linux/amd64 --push -t msanjeevi/prom-snow-webhook .
docker buildx build --platform linux/amd64,linux/arm64 --push -t msanjeevi/prom-snow-webhook .


docker run -d --env-file .env -p 8080:8080 --name prom-snow  msanjeevi/prom-snow-webhook
```

## Openshift deployment

```sh
oc create secret generic prom-snow-secret --from-env-file=.env

oc apply -f deployment.yaml
```

```json
{
    "description": "f'{alert.annotations.description}'",
    "work_notes": "f'Alert fired at {alert.startsAt}. {alert.labels.work_notes}, check {alert.generatorURL}'",
    "priority": "4-low",
    "impact": "4-low",
    "urgency": "4-low",
    "state": "New",
    "u_affected_user": "OpenshiftUser",
    "assignment_group": "ORG-SP-Openshift",
    "caller_id": "OpenshiftUser",
    "category": "Failure",
    "subcategory": "Monitoring",
    "service_offering": "OpenShift Runtime",
    "u_routing_group": "ORG-SP-Openshift",
    "u_subject_area": "Openshift",
    "u_open_type": "Openshift"
}
```

```sh
oc create configmap snow-mandatory-fields --from-file=mandatory.json
```