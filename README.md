# Rhino

Rhino is a mesos framework for launching dockerized batch jobs. It is used by
Appsoma's welder project for mesos interaction.

Rhino is a temporary solution until either another framework such as
Singularity or Chronos are a bit more stable and can replace it.


## Install

The easiest way to run rhino is using a docker container.

	git pull git://github.com/appsoma/rhino.git
	cd rhino
	./rhino_in_container.bash

It will ask you two questions. The first is the IP and port of zookeeper. It defaults
to assuming that it is on the current machine on the default port of 2181.

Second question is the full path to where you want to store the database files.

It will then start a mongodb and Rhino in docker containers. To see if they
are running properly:

	docker ps

You should see two containers running: "rhino_prod" and "rhino_mongo_prod"

If you need to stop the service.

	docker kill rhino_prod rhino_mongo_prod
	docker rm rhino_prod rhino_mongo_prod

Then you can re-run the ./rhino_in_container.bash script to restart them.


## API

| Action     | Path                                                 | Description
-------------|------------------------------------------------------|--------------------------------------
POST         | [/tasks](docs/post_tasks.md)                         | Create a task
GET          | [/tasks](docs/get_tasks.md)                          | Fetch all tasks status
GET          | [/tasks/:taskId](docs/get_tasks_taskid.md)           | Fetch all status for given task
DELETE       | [/tasks/:taskId](docs/delete_tasks_taskid.md)        | Cancel a task

