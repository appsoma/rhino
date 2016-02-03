# Rhino

Rhino is a mesos framework for launching dockerized batch jobs. It is used by
Appsoma's welder project for mesos interaction.

Rhino is a temporary solution until either another framework such as
Singularity or Chronos are a bit more stable and can replace it.


## Install

You will need a running MongoDB server available on the network for session and job information.

The easiest way to run rhino is using a docker container.

	docker run -d -P -e RHINO_MONGO_HOST=mongo.marathon.mesos -e RHINO_MONGO_PORT=27017 appsoma:rhino

To run on a local machine, you will need to install the [Mesos Python Egg](https://open.mesosphere.com/downloads/mesos/) and `pip install pymongo`

## API

| Action     | Path                                                 | Description
-------------|------------------------------------------------------|--------------------------------------
POST         | [/tasks](docs/post_tasks.md)                         | Create a task
GET          | [/tasks](docs/get_tasks.md)                          | Fetch all tasks status
GET          | [/tasks/:taskId](docs/get_tasks_taskid.md)           | Fetch all status for given task
DELETE       | [/tasks/:taskId](docs/delete_tasks_taskid.md)        | Cancel a task

