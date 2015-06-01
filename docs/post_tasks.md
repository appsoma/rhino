### POST /tasks

Launch a new task with the following JSON block.

		{
			"name": "some_task_name",
			"command": "some_command",
			"user": "some_user",
				// Optional, default=root
			"environment": {
				// Optional
				"some_environment_variable": "value"
			},
			"requirements": {
				"cpus": 1,
				"mem": 512
			},
			"container": {
				// Optional
				"image": "a_docker_container",
				"volumes": [
					"/host:/guest:ro"
				]
			}
		}
