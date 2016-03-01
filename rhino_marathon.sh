#!/usr/bin/env bash
ACTION=""
GENERATE_ONLY=1

while [[ $# > 0 ]]
do
  key="$1"
  case $key in
    --generate)
      GENERATE_ONLY=0
    ;;
    *)
      ACTION="$key"
    ;;
  esac
  shift
done

if [ "$ACTION" != "start" ] && [ "$ACTION" != "restart" ] && [ "$ACTION" != "stop" ]; then
	echo "Options are start, stop, restart"
	exit 1
fi

if [ "$ACTION" == "stop" ] || [ "$ACTION" == "restart" ]; then
	curl -H "Content-Type:application/json" -X DELETE http://master.mesos:8080/v2/apps/rhino
fi

if [ "$ACTION" == "start" ] || [ "$ACTION" == "restart" ]; then
	cat >/tmp/rhino_run.json <<EOL
{
	"id": "/rhino",
	"cpus": 0.25,
	"mem": 512.0,
	"instances": 1,
	"env": {
		"RHINO_MONGO_HOST": "mongo.marathon.slave.mesos",
		"RHINO_MONGO_PORT": "27017",
		"RHINO_ZOOKEEPER_HOST_LIST": "master.mesos:2181"
	},
	"constraints": [ ["node_type", "LIKE", "master"] ],
	"container": {
		"type": "DOCKER",
		"docker": {
			"image": "appsoma/rhino:v1",
			"network": "BRIDGE",
			"portMappings": [
				{
					"containerPort": 8899,
					"hostPort": 8899,
					"protocol": "tcp"
				}
			]
		}
	},
	"healthChecks": [{
	    "protocol": "HTTP",
	    "path": "/health",
	    "gracePeriodSeconds": 600,
	    "intervalSeconds": 30,
	    "portIndex": 0,
	    "timeoutSeconds": 1,
	    "maxConsecutiveFailures": 2
	}]
}
EOL
    if [ $GENERATE_ONLY != 0 ]; then
        curl -H "Content-Type:application/json" -X POST --data @/tmp/rhino_run.json http://master.mesos:8080/v2/apps
    else
    	echo "JSON file dumped to /tmp/rhino_run.json"
    fi
fi
echo
