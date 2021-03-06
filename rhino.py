#!/usr/bin/env python
import os
import signal
import sys
import json
import threading
import re
import pymongo
import random
import string
import urllib2
from BaseHTTPServer import BaseHTTPRequestHandler, HTTPServer
from mesos.native import MesosSchedulerDriver
from mesos.interface import Scheduler
from mesos.interface import mesos_pb2

config = {}
config['mongodb'] = {}
if os.environ.get("RHINO_MONGO_HOST", None) is not None:
    config['mongodb']['host'] = os.environ.get("RHINO_MONGO_HOST")
if os.environ.get("RHINO_MONGO_PORT", None) is not None:
    config['mongodb']['port'] = int(os.environ.get("RHINO_MONGO_PORT"))
if os.environ.get("RHINO_ZOOKEEPER_HOST_LIST", None) is not None:
    config['zookeeper_hosts'] = os.environ.get("RHINO_ZOOKEEPER_HOST_LIST")

if (not 'port' in config['mongodb']) and (not 'host' in config['mongodb']):
    try:
        config['mongodb']['host'] = sys.argv[1]
        config['mongodb']['port'] = int(sys.argv[2])
    except IndexError as e:
        print "Mongo DB host and port not defined, using mongo.marathon.mesos:27017 by default"
        config['mongodb']['host'] = "mongo.marathon.mesos"
        config['mongodb']['port'] = 27017

if 'zookeeper_hosts' not in config:
    config['zookeeper_hosts'] = "master.mesos:2181"

mesos_lock = threading.Lock()

mesos_driver = None


def random_string(length=16):
    return ''.join(random.choice(string.ascii_uppercase + string.digits) for _ in range(length))


client = pymongo.MongoClient('mongodb://' + config['mongodb']['host'], config['mongodb']['port'])
db = client.rhino

last_registry = None
leader_hostname = ""
leader_port = ""


class HttpHandler(BaseHTTPRequestHandler):
    def return_exception(self, e):
        self.send_response(404)
        json_block = json.dumps({"error": str(e)})
        self.send_header('content-type', 'application/json')
        self.send_header('content-length', str(len(json_block)))
        self.end_headers()
        self.wfile.write(json_block)

    def do_POST(self):
        try:
            global last_registry
            global leader_hostname
            global leader_port
            last_registry = json.loads(urllib2.urlopen("http://" + leader_hostname + ":" + leader_port + "/registrar(1)/registry").read())
        except Exception as exc:
            print "Error while reading registry from Mesos Leader", exc

        try:
            if self.path == '/tasks':
                content_len = int(self.headers.getheader('content-length', 0))
                content = self.rfile.read(content_len)
                post = json.loads(content)

                # VALIDATE the post block
                if 'name' not in post:
                    raise Exception("'name' missing")
                if 'command' not in post:
                    raise Exception("'command' missing")
                if 'requirements' not in post:
                    raise Exception("'requirements' missing")
                if 'environment' in post:
                    if not isinstance(post['environment'], dict):
                        raise Exception("'environment' must be a dict")
                if 'container' in post:
                    if not isinstance(post['container'], dict):
                        raise Exception("'container' must be a dict")
                    if 'image' not in post['container']:
                        raise Exception("'container' must include an image")
                    if 'volumes' in post['container']:
                        if not isinstance(post['container']['volumes'], list):
                            raise Exception("'volumes' must be a list")
                        for volume in post['container']['volumes']:
                            if not isinstance(volume, basestring):
                                raise Exception("'volumes' must be a list of strings")
        except Exception as exc:
            print "Exception while validating post block", exc
            import traceback
            traceback.print_exc()
            self.return_exception(exc)

        try:
            # CHECK if there exists any slave that is capable of handling the requested task
            # IF not then we need to return a friendly error.
            if last_registry:
                found_slave_that_fits = False
                for slave in last_registry['slaves']['slaves']:
                    cpus = 0
                    mem = 0
                    disk = 0
                    for res in slave['info']['resources']:
                        if res['name'] == 'cpus':
                            cpus = int(res['scalar']['value'])
                        if res['name'] == 'mem':
                            mem = int(res['scalar']['value'])
                        if res['name'] == 'disk':
                            disk = int(res['scalar']['value'])
                    if int(post['requirements']['cpus']) <= cpus and int(
                            post['requirements']['mem']) <= mem and int(post['requirements']['disk']) <= disk:
                        found_slave_that_fits = True
                        break
                if not found_slave_that_fits:
                    raise Exception("No slave is capable of handling that request")

                post['state'] = 'PENDING'

                # CHECK if any dependency is already dead
                print "POST", json.dumps(post, indent=4)
                for depends in post.get('depends_on', []):
                    res = db.rhino_tasks.find_one({"name": depends})
                    if res is not None and 'state' in res:
                        if res['state'] == 'ERROR' or res['state'] == 'KILLED':
                            post['state'] = 'KILLED'

                # @TODO: Add a unique index on post by name
                # and check that it exceptions if you try to add a duplicate
                db.rhino_tasks.insert_one(post)

                json_block = json.dumps({'posted': 'someval1'})
                self.send_response(200)
                self.send_header('content-type', 'application/json')
                self.send_header('content-length', str(len(json_block)))
                self.end_headers()
                self.wfile.write(json_block)
            else:
                raise Exception("Not found")

        except Exception as exc:
            print "Error submitting job", exc
            import traceback
            traceback.print_exc()
            self.return_exception(exc)

    def do_GET(self):
        try:
            match = re.search(r'^/tasks(/[^/]+)?$', self.path)
            if match:
                if match.group(1):
                    name = match.group(1)[1:]
                    res = db.rhino_tasks.find_one({"name": name})
                    del res['_id']
                else:
                    res = []
                    for task in db.rhino_tasks.find():
                        del task['_id']
                        res.append(task)

                json_block = json.dumps(res)
                self.send_response(200)
                self.send_header('content-type', 'application/json')
                self.send_header('content-length', str(len(json_block)))
                self.end_headers()
                self.wfile.write(json_block)
            elif self.path == '/health':
                json_block = json.dumps({'status': 'ok'})
                self.send_response(200)
                self.send_header('content-type', 'application/json')
                self.send_header('content-length', str(len(json_block)))
                self.end_headers()
                self.wfile.write(json_block)
            else:
                raise Exception("Not found")
        except Exception as e:
            self.return_exception(e)

    def do_DELETE(self):
        try:
            match = re.search(r'^/tasks/(.*)$', self.path)
            if match:
                task = db.rhino_tasks.find_one({'name': match.group(1)})

                if task['state'] == "PENDING":
                    # It hasn't made it to mesos yet, mark as killed
                    db.rhino_tasks.update({'name': match.group(1)}, {'$set': {'state': 'KILLED'}})

                mesos_lock.acquire()
                try:
                    task_id = mesos_pb2.TaskID()
                    task_id.value = task['mesos_id']
                    mesos_driver.killTask(task_id)
                except Exception as e:
                    raise e
                finally:
                    mesos_lock.release()

                # db.rhino_tasks.update( { 'name':match.group(1) }, { '$set':{'state':'KILLED'} } )

                res = {"killed": match.group(1)}
                json_block = json.dumps(res)
                self.send_response(200)
                self.send_header('content-type', 'application/json')
                self.send_header('content-length', str(len(json_block)))
                self.end_headers()
                self.wfile.write(json_block)
            else:
                raise Exception("Not found")
        except Exception as e:
            self.return_exception(e)

    def log_message(self, format_str, *args):
        print(args)


def web_server():
    server = HTTPServer(('', 8899), HttpHandler)
    server.serve_forever()


class AppsomaRhinoScheduler(Scheduler):

    @staticmethod
    def disconnected(driver):
        print "DISCONNECTED"

    @staticmethod
    def error(driver, error_msg):
        print "ERROR", error_msg

    @staticmethod
    def executorLost(driver, executor_id, slave_id, status):
        print "EXECUTOR LOST", executor_id, status

    @staticmethod
    def frameworkMessage(driver, executor_id, slave_id, data):
        print "FRAMEWORK MSG", executor_id, data

    @staticmethod
    def offerRescinded(driver, offer_id):
        print "OFFER RESCIND", offer_id

    @staticmethod
    def registered(driver, framework_id, master_info):
        global leader_hostname
        global leader_port
        leader_hostname = master_info.hostname
        leader_port = str(master_info.port)
        print "REGISTERED " + framework_id.value + ", With leader at " + leader_hostname + ":" + leader_port

    @staticmethod
    def reregistered(driver, master_info):
        global leader_hostname
        global leader_port
        leader_hostname = master_info.hostname
        leader_port = master_info.port
        print "RE-REGISTERED With leader at " + leader_hostname + ":" + leader_port

    @staticmethod
    def resourceOffers(driver, offers):
        tasks = db.rhino_tasks.find({'state': 'PENDING'})
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

                try:
                    total_depends = 0
                    success_depends = 0
                    for depends in task.get('depends_on', []):
                        depend_doc = db.rhino_tasks.find_one({'name': depends})
                        if depend_doc:
                            total_depends += 1
                            if depend_doc.get('state', '') == 'SUCCESS':
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
                    except KeyError as e:
                        pass

                    try:
                        mem = float(task['requirements']['mem'])
                    except KeyError as e:
                        pass

                    try:
                        disk = float(task['requirements']['disk'])
                    except KeyError as e:
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
                            # print "image", d.image

                            if 'user' in task.get('container'):
                                user_param = d.parameters.add()
                                user_param.key = "user"
                                user_param.value = task.get('container')['user']

                            c = mesos_pb2.ContainerInfo()
                            c.type = mesos_pb2.ContainerInfo.DOCKER
                            c.docker.MergeFrom(d)

                            vol = c.volumes.add()
                            vol.host_path = "/etc/passwd"
                            vol.container_path = "/etc/passwd"
                            vol.mode = mesos_pb2.Volume.RO

                            vol = c.volumes.add()
                            vol.host_path = "/etc/group"
                            vol.container_path = "/etc/group"
                            vol.mode = mesos_pb2.Volume.RO

                            for volume in task['container'].get('volumes', []):
                                vol_split = volume.split(':')
                                vol = c.volumes.add()
                                vol.host_path = vol_split[0]
                                vol.container_path = vol_split[1]
                                if vol_split[2].lower() == "ro":
                                    vol.mode = mesos_pb2.Volume.RO
                                elif vol_split[2].lower() == "rw":
                                    vol.mode = mesos_pb2.Volume.RW
                                else:
                                    raise Exception("Illegal volume mode")
                                    # print "VOL", vol.host_path, vol.container_path, vol.mode

                            mesos_task.container.MergeFrom(c)

                        mesos_task.command.value = task['command']
                        print "cmd", mesos_task.command.value

                        ret = driver.launchTasks(offer.id, [mesos_task])

                        # @TODO: Error handing for this whole function
                        print "SUBMITTING", task['name'], "LAUNCH RET", ret, "ID", mesos_id
                        db.rhino_tasks.update({'_id': task['_id']}, {'$set': {'state': 'STAGING', 'mesos_id': mesos_id}})

                        accepted = True
                        break
                except Exception as exc:
                    import traceback
                    traceback.print_exc()
                    print "Exception in task", exc
                    try:
                        print "ID", mesos_id
                    except Exception as exc:
                        print exc
                        mesos_id = "NONE"
                    # KILL this task and go to next
                    db.rhino_tasks.update({'_id': task['_id']},
                                          {'$set': {'state': 'ERROR', 'mesos_id': mesos_id, 'message': str(exc)}})

            if not accepted:
                mesos_lock.acquire()
                try:
                    driver.declineOffer(offer.id)
                except Exception as e:
                    raise e
                finally:
                    mesos_lock.release()

    @staticmethod
    def slaveLost(driver, slave_id):
        print "SLAVE LOST", slave_id

    @staticmethod
    def statusUpdate(driver, status):
        print "STATUS", status
        state = "UNKNOWN MESOS STATE"

        ret_code = -9999
        kill_depends = False
        message = 'No message'

        if status.state == mesos_pb2.TASK_RUNNING:
            state = "RUNNING"

        elif status.state == mesos_pb2.TASK_KILLED:
            state = 'KILLED'
            kill_depends = True

        elif status.state == mesos_pb2.TASK_LOST:
            state = 'ERROR'
            message = status.message
            kill_depends = True

        elif status.state == mesos_pb2.TASK_FINISHED:
            state = 'SUCCESS'
            ret_code = 0
            message = status.message
        elif status.state == mesos_pb2.TASK_FAILED:
            match = re.search(r'exited with status (\d+)$', status.message)
            if match:
                ret_code = int(match.group(1))
                print "RET CODE", ret_code
            else:
                print "NO MATCH FOR RETURN CODE, Parse error in status?: " + status.message

            state = 'ERROR'
            message = status.message
            kill_depends = True

        else:
            state = 'ERROR'
            message = "Unknown mesos status code " + str(status.state)

        if kill_depends:
            tasks = list(db.rhino_tasks.find({'state': 'PENDING'}))
            doc = db.rhino_tasks.find_one({'mesos_id': status.task_id.value})

            def kill_those_that_depend_on(name):
                # print "kill_those_that_depend_on", name
                # print "TASKS=", tasks
                for task in tasks:
                    # print "EXAMINE", task.get('name')
                    for depends in task.get('depends_on', []):
                        if depends == name:
                            # print "KILLING", task['name'], "BECAUSE IT DEPENDS ON", name

                            mesos_lock.acquire()
                            try:
                                if task.get('mesos_id', None):
                                    task_id = mesos_pb2.TaskID()
                                    task_id.value = task['mesos_id']
                                    mesos_driver.killTask(task_id)
                            except Exception as e:
                                raise e
                            finally:
                                mesos_lock.release()

                            db.rhino_tasks.update({'name': task['name']}, {'$set': {'state': 'KILLED'}})
                            kill_those_that_depend_on(task['name'])

            kill_those_that_depend_on(doc['name'])

        db.rhino_tasks.update({'mesos_id': status.task_id.value},
                              {'$set': {'state': state, 'retCode': ret_code, 'message': message}})

if __name__ == '__main__':
    try:
        web_server_thread = threading.Thread(target=web_server, args=())
        web_server_thread.start()

        framework = mesos_pb2.FrameworkInfo()
        framework.user = ""  # Have Mesos fill in the current user.
        framework.name = "rhino"
        mesos_driver = MesosSchedulerDriver(
            AppsomaRhinoScheduler(),
            framework,
            "zk://" + config['zookeeper_hosts'] + "/mesos"
        )
        mesos_driver.run()
    except KeyboardInterrupt:
        print "KeyboardInterrupt"
        os.kill(os.getpid(), 9)
