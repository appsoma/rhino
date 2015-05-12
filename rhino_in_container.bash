#!/usr/bin/env bash

ZK_IP=`/sbin/ifconfig eth0 | grep 'inet addr:' | cut -d: -f2 | awk '{ print $1}'`

DEVSTR="prod"
if [ "$1" = "--dev" ] || [ "$2" = "--dev" ]; then
  DEVSTR="dev"
fi

if [ "$1" = "--stop" ] || [ "$2" = "--stop" ]; then
  echo "Killing previously running containers. Ignore any error messages..."
  docker kill rhino_mongo_${DEVSTR}
  docker rm rhino_mongo_${DEVSTR}
  docker kill rhino_${DEVSTR}
  docker rm rhino_${DEVSTR}
  exit 0
fi

docker ps | grep welder_${DEVSTR}
if [ "$?" = "0" ]; then
  echo ""
  echo "Killing previously running rhino container. Ignore any error messages..."
  docker kill rhino_${DEVSTR}
  docker rm rhino_${DEVSTR}
fi

docker ps | grep rhino_mongo_${DEVSTR} > /dev/null
if [ "$?" = "0" ]; then
  DB_RUNNING=1
else
  DB_RUNNING=0
fi

if [ "$1" = "--no-questions" ]; then
  if [ -f "./rhino_container_config" ]; then
    source ./rhino_container_config
  else
    echo ""
    echo "FATAL"
    echo "  You specified --no-questions but you haven't previously run the"
    echo "  install and therefore you can not continue."
    echo ""
    exit 1
  fi
else
  if [ -f "./rhino_container_config" ]; then
    source ./rhino_container_config
  fi

  if [ "$ZK_IP" = "" ]; then
    echo "Enter a new IP address for zookeeper:"
    read ZK_IP
  else
    echo "Enter a new IP address for zookeeper or press ENTER to accept: ${ZK_IP}"
    read _ZK_IP
    if [ "$_ZK_IP" != "" ]; then
      ZK_IP="$_ZK_IP"
    fi
  fi

  if [ "$DB_RUNNING" = "0" ]; then
    if [ "$DB_FOLDER" = "" ]; then
      echo "Enter a new database folder:"
      read DB_FOLDER
    else
      echo "Enter a new database folder or press ENTER to accept: ${DB_FOLDER}"
      read _DB_FOLDER
      if [ "$_DB_FOLDER" != "" ]; then
        DB_FOLDER="$_DB_FOLDER"
      fi
    fi
  fi

  echo ""
  echo "Saving your configuration to rhino_container_config..."
  echo "ZK_IP=${ZK_IP}" > rhino_container_config
  echo "DB_FOLDER=${DB_FOLDER}" >> rhino_container_config
fi

cat > ./rhino_config.json << EOL
{
  "mongodb": {
    "host": "mongo",
    "port": 27017
  },
  "zk_ip": "${ZK_IP}"
}
EOL

if [ "$DB_RUNNING" = "1" ]; then
  echo "Rhino mongo container already running."
else
  echo "Starting rhino_mongo_${DEVSTR} container...."
  docker run -v ${DB_FOLDER}:/data/db:rw --name rhino_mongo_${DEVSTR} -d mongo mongod --smallfiles
fi


if [ "$DEVSTR" = "dev" ]; then
  CWD=`pwd`
  MAP_RHINO_FOLDER="-v $CWD:/rhino_repo:ro"
  echo "#!/usr/bin/env bash" > ./start-inside.bash
  cat >> ./start-inside.bash << EOL
    touch /rhino/mesos/__init__.py
    export PYTHONPATH=/rhino/mesos_py_2
    cd /rhino
    cp /rhino_repo/rhino.py .
    cat /config/config.json
    python -u rhino.py /config/config.json
EOL
else
  MAP_RHINO_FOLDER=""
  echo "#!/usr/bin/env bash" > ./start-inside.bash
  cat >> ./start-inside.bash << EOL
    git clone git://github.com/appsoma/rhino rhino_repo
    touch /rhino/mesos/__init__.py
    export PYTHONPATH=/rhino/mesos_py_2
    cd /rhino
    cp /rhino_repo/rhino.py .
    cat /config/config.json
    python -u rhino.py /config/config.json
EOL
fi

chmod +x ./start-inside.bash

docker ps | grep rhino
if [ "$?" = "0" ]; then
  docker kill rhino
  docker rm rhino
fi

docker run \
  --name rhino_${DEVSTR} \
  -v /etc/passwd:/etc/passwd:ro \
  -v /etc/group:/etc/group:ro \
  -it \
  $MAP_RHINO_FOLDER \
  -v `pwd`/start-inside.bash:/rhino/start-inside.bash:ro \
  -v `pwd`/rhino_config.json:/config/config.json:ro \
  --link rhino_mongo_${DEVSTR}:mongo \
  -p 8899:8899 \
  container-registry.appsoma.com/rhino2 \
  /rhino/start-inside.bash

