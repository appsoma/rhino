#!/usr/bin/env bash

echo "#!/usr/bin/env bash" > ./start-inside.bash
cat >> ./start-inside.bash << EOL
	touch /rhino/mesos/__init__.py
	cp /rhino/source/rhino.py /rhino
	export PYTHONPATH=/rhino/mesos_py_2
	python -u rhino.py
EOL
chmod +x ./start-inside.bash

docker kill rhino
docker rm rhino
docker run \
  --name rhino \
  -it \
  -v `pwd`:/rhino/source:ro \
  --link welder_mongo:mongo \
  -w /rhino \
  -p 8899:8899 \
  container-registry.appsoma.com/rhino \
  ./source/start-inside.bash

