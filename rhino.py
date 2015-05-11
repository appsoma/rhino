#!/usr/bin/env python
#import logging
#import uuid
import time
import os
import signal
import sys
import json
import threading
import re
import pymongo
import random
import string
from BaseHTTPServer import BaseHTTPRequestHandler,HTTPServer

#import mesos_py_2 as mesos
from mesos_py_2.native import MesosSchedulerDriver
from mesos.interface import Scheduler
from mesos.interface import mesos_pb2

#import mesos.interface
#print mesos.interface.__file__

mesos_lock = threading.Lock()

mesos_driver = None

def random_string(length=16):
	return ''.join(random.choice(string.ascii_uppercase + string.digits) for _ in range(length))

client = pymongo.MongoClient('mongodb://localhost',27017)
db = client.appsoma_rhino

class HttpHandler(BaseHTTPRequestHandler):
	def returnException( self, e ):
		self.send_response(404)
		json_block = json.dumps( { "error":str(e) } )
		self.send_header('content-type', 'application/json')
		self.send_header('content-length', str(len(json_block)))
		self.end_headers()
		self.wfile.write( json_block )

	def do_POST(self):
		"""
		{
			"name": "some_step_name",
			"command": "some_command",
			"depends_on": [
				// Optional
				"other_job_name"
			],
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
		"""

		try:
			if self.path == '/tasks':
				content_len = int(self.headers.getheader('content-length', 0))
				post = json.loads( self.rfile.read(content_len) )

				# VALIDATE the post block
				if 'name' not in post: raise Exception( "'name' missing" )
				if 'command' not in post: raise Exception( "'command' missing" )
				if 'requirements' not in post: raise Exception( "'requirements' missing" )
				if 'environment' in post:
					if not isinstance(post['environment'],dict):
						raise Exception( "'environment' must be a dict" )
				if 'container' in post:
					if not isinstance(post['container'],dict):
						raise Exception( "'container' must be a dict" )
					if 'image' not in post['container']:
						raise Exception( "'container' must include an image" )
					if 'volumes' in post['container']:
						if not isinstance(post['container']['volumes'],list):
							raise Exception( "'volumes' must be a list" )
						for volume in post['container']['volumes']:
							if not isinstance(volume,basestring):
								raise Exception( "'volumes' must be a list of strings" )


				post['state'] = 'PENDING'

				# @TODO: Add a unique index on post by name
				# and check that it exceptions if you try to add a duplicate
				db.rhino_tasks.insert_one(post)

				json_block = json.dumps( {'posted':'someval1'} )
				self.send_response(200)
				self.send_header('content-type', 'application/json')
				self.send_header('content-length', str(len(json_block)))
				self.end_headers()
				self.wfile.write( json_block )

				# Request
				request = mesos_pb2.Request()
				cpus = request.resources.add()
				cpus.name = "cpus"
				cpus.type = mesos_pb2.Value.SCALAR
				cpus.scalar.value = 1

				mem = request.resources.add()
				mem.name = "mem"
				mem.type = mesos_pb2.Value.SCALAR
				mem.scalar.value = 512

				mesos_lock.acquire()
				try:
					mesos_driver.requestResources( request )
				except Exception as e:
					raise e
				finally:
					mesos_lock.release()
			else:
				raise Exception("Not found")
		except Exception as e:
			self.returnException( e )


	def do_GET(self):
		try:
			match = re.search( r'^/tasks(/[^/]+)?$', self.path )
			if match:
				if match.group(1):
					name = match.group(1)[1:]
					res = db.rhino_tasks.find_one({"name":name})
					del res['_id']
				else:
					res = []
					for task in db.rhino_tasks.find():
						del task['_id']
						res.append( task )

				json_block = json.dumps( res )
				self.send_response(200)
				self.send_header('content-type', 'application/json')
				self.send_header('content-length', str(len(json_block)) )
				self.end_headers()
				self.wfile.write( json_block )
			else:
				raise Exception("Not found")
		except Exception as e:
			self.returnException( e )

	def do_DELETE(self):
		try:
			match = re.search( r'^/tasks/(.*)$', self.path )
			if match:
				task = db.rhino_tasks.find_one( { 'name':match.group(1) } )
				mesos_lock.acquire()
				try:
					task_id = mesos_pb2.TaskID()
					task_id.value = task['mesos_id']
					mesos_driver.killTask( task_id )
				except Exception as e:
					raise e
				finally:
					mesos_lock.release()

				#db.rhino_tasks.update( { 'name':match.group(1) }, { '$set':{'state':'KILLED'} } )

				res = { "killed":match.group(1) }
				json_block = json.dumps( res )
				self.send_response(200)
				self.send_header('content-type', 'application/json')
				self.send_header('content-length', str(len(json_block)) )
				self.end_headers()
				self.wfile.write( json_block )
			else:
				raise Exception("Not found")
		except Exception as e:
			self.returnException( e )

	def log_message( self, format, *args ):
		#print "LOG", format, args
		return

def web_server():
	server = HTTPServer( ('', 8899), HttpHandler )
	server.serve_forever()

class AppsomaRhinoScheduler(Scheduler):
	def disconnected( self, driver ):
		print "DISCONNECTED"

	def error( self, driver, error_msg ):
		print "ERROR", error_msg

	def executorLost( self, driver, executor_id, slave_id, status ):
		print "EXECUTOR LOST", executor_id, status

	def frameworkMessage( self, driver, executor_id, slave_id, data ):
		print "FRAMEWWORK MSG", executor_id, data

	def offserRescinded( self, driver, offer_id ):
		print "OFFER RESCIND", offer_id

	def registered(self, driver, framework_id, master_info):
		print "REGISTERED", framework_id

	def reregistered(self, driver, master_info):
		print "REREGISTERED", framework_id

	def resourceOffers(self, driver, offers):
		tasks = db.rhino_tasks.find( { 'state':'PENDING' } )
		for offer in offers:
			offer_cpus = 0
			offer_mem = 0
			offer_disk = 0
			for res in offer.resources:
				if res.name == "cpus":
					offer_cpus = res.scalar.value
				if res.name == "mem":
					offer_mem = res.scalar.value
				if res.name == "disk":
					offer_disk = res.scalar.value

			# FIND a pending task that has no waiting dependencies
			accepted = False
			for task in tasks:
				#if task.get('state') != "PENDING":
				#	continue

				total_depends = 0
				success_depends = 0
				for depends in task.get('depends_on',[]):
					depend_doc = db.rhino_tasks.find_one( {'name':depends} )
					if depend_doc:
						total_depends += 1
						if depend_doc.get('state','') == 'SUCCESS':
							success_depends += 1
					else:
						print "Ignored reference to", depends

				if success_depends != total_depends:
					continue

				cpus = 1
				mem = 512
				disk = 0

				try:
					cpus = float(task['requirements']['cpu'])
				except:
					pass

				try:
					mem = float(task['requirements']['mem'])
				except:
					pass

				try:
					disk = float(task['requirements']['disk'])
				except:
					pass

				if cpus <= offer_cpus and mem <= offer_mem and disk <= offer_disk:
					mesos_task = mesos_pb2.TaskInfo()

					mesos_task.name = task['name']

					mesos_id = random_string()
					mesos_task.task_id.value = str(mesos_id)
					mesos_task.slave_id.value = offer.slave_id.value

					mesos_task_cpus = mesos_task.resources.add()
					mesos_task_cpus.name = "cpus"
					mesos_task_cpus.type = mesos_pb2.Value.SCALAR
					mesos_task_cpus.scalar.value = cpus

					mesos_task_mem = mesos_task.resources.add()
					mesos_task_mem.name = "mem"
					mesos_task_mem.type = mesos_pb2.Value.SCALAR
					mesos_task_mem.scalar.value = mem

					mesos_task_disk = mesos_task.resources.add()
					mesos_task_disk.name = "disk"
					mesos_task_disk.type = mesos_pb2.Value.SCALAR
					mesos_task_disk.scalar.value = disk

					if task.get('container'):
						d = mesos_pb2.ContainerInfo.DockerInfo()
						d.image = task['container']['image']

						if 'user' in task.get('container'):
							user_param = d.parameters.add()
							user_param.key = "user"
							user_param.value = task.get('container')['user']
							pass

						c = mesos_pb2.ContainerInfo()
						c.type = mesos_pb2.ContainerInfo.DOCKER
						c.docker.MergeFrom( d )

						vol = c.volumes.add()
						vol.host_path = "/etc/passwd"
						vol.container_path = "/etc/passwd"
						vol.mode = mesos_pb2.Volume.RO

						vol = c.volumes.add()
						vol.host_path = "/etc/group"
						vol.container_path = "/etc/group"
						vol.mode = mesos_pb2.Volume.RO

						for volume in task['container'].get('volumes',[]):
							vol_split = volume.split(':')
							vol = c.volumes.add()
							vol.host_path = vol_split[0]
							vol.container_path = vol_split[1]
							if vol_split[2].lower() == "ro":
								vol.mode = mesos_pb2.Volume.RO
							elif vol_split[2].lower() == "rw":
								vol.mode = mesos_pb2.Volume.RW
							else:
								raise Exception( "Illegal volume mode" )

						mesos_task.container.MergeFrom( c )

					mesos_task.command.value = task['command']
					print "cmd", mesos_task.command.value

					ret = driver.launchTasks( offer.id, [ mesos_task ] )

					# @TODO: Error handing for this whole function
					print "SUBMITTING", task['name'], "LAUNCH RET", ret
					db.rhino_tasks.update( {'_id':task['_id']}, { '$set':{'state':'STAGING','mesos_id':mesos_id} } )

					accepted = True
					break

			if not accepted:
				mesos_lock.acquire()
				try:
					driver.declineOffer( offer.id )
				except Exception as e:
					raise e
				finally:
					mesos_lock.release()

	def slaveLost(self, driver, slave_id):
		print "SLAVE LOST", slave_id

	def statusUpdate(self, driver, status):
		print "STATUS", status
		state = "UNKNOWN MESOS STATE"
		ret_code = -9999
		kill_depends = False

		if status.state == mesos_pb2.TASK_RUNNING:
			state = "RUNNING"

		if status.state == mesos_pb2.TASK_FINISHED or status.state == mesos_pb2.TASK_FAILED:
			match = re.search( r'^Command exited with status (\d+)$', status.message )
			if match:
				ret_code = int(match.group(1))
				print "RET CODE", ret_code
			else:
				print "NO MATCH FOR RETURN CODE"

			if ret_code == 0 and status.state == mesos_pb2.TASK_FINISHED:
				state = 'SUCCESS'
			else:
				state = 'ERROR'
				kill_depends = True

		elif status.state == mesos_pb2.TASK_KILLED:
			state = 'KILLED'
			kill_depends = True

		if kill_depends:
			tasks = db.rhino_tasks.find( { 'state':'PENDING' } )
			doc = db.rhino_tasks.find_one( {'mesos_id':status.task_id.value} )

			def kill_those_that_depend_on( name ):
				#print "kill_those_that_depend_on", name
				for task in tasks:
					for depends in task.get('depends_on',[]):
						if depends == name:
							#print "KILLING", task['name'], "BECAUSE IT DEPENDS ON", name

							mesos_lock.acquire()
							try:
								if task.get('mesos_id',None):
									task_id = mesos_pb2.TaskID()
									task_id.value = task['mesos_id']
									mesos_driver.killTask( task_id )
							except Exception as e:
								raise e
							finally:
								mesos_lock.release()

							db.rhino_tasks.update( {'name':task['name']}, { '$set':{'state':'KILLED'} } )
							kill_those_that_depend_on( task['name'] )

			kill_those_that_depend_on( doc['name'] )

		db.rhino_tasks.update( {'mesos_id':status.task_id.value}, { '$set':{'state':state,'retCode':ret_code} } )
		driver.acknowledgeStatusUpdate(status)


def sigTerm(signum, frame):
	os.kill( os.getpid(), 9 )

if __name__ == '__main__':
	signal.signal(signal.SIGTERM, sigTerm)
	try:
		web_server_thread = threading.Thread( target=web_server, args=() )
		web_server_thread.start()

		framework = mesos_pb2.FrameworkInfo()
		framework.user = ""  # Have Mesos fill in the current user.
		framework.name = "appsoma_rhino"
		mesos_driver = MesosSchedulerDriver(
			AppsomaRhinoScheduler(),
			framework,
			"zk://10.240.243.155:2181/mesos"  # assumes running on the master
		)
		mesos_driver.run()
	except KeyboardInterrupt:
		print "KeyboardInterrupt"
		os.kill( os.getpid(), 9 )
