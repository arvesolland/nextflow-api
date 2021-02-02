#!/usr/bin/env python3

import asyncio
import os
import subprocess

import env



def run_workflow(workflow, work_dir, resume):
	# save current directory
	prev_dir = os.getcwd()

	# change to workflow directory
	os.chdir(work_dir)

	run_name = 'workflow-%s-%04d' % (workflow['_id'], workflow['attempts'])

	# Create a new shell script that can be sent to SLURM via sbatch
	run_script = os.path.join(work_dir, run_name+'.sh')		
	if os.path.exists(run_script):
		os.remove(run_script)


	

		

	# launch workflow, wait for completion
	if env.NXF_EXECUTOR == 'k8s':
		args = [
			'nextflow',
			'-config', 'nextflow.config',
			'-log', os.path.join(workflow['output_dir'], 'nextflow.log'),
			'kuberun',
			workflow['pipeline'],
			'-ansi-log', 'false',
			'-latest','1',
			'-name', run_name,
			'-profile', workflow['profiles'],
			'-revision', workflow['revision'],
			'-volume-mount', env.PVC_NAME
		]

	elif env.NXF_EXECUTOR == 'local':
		
		args = [
			'srun',
			'nextflow',
			'-config', 'nextflow.config',
			'-log', os.path.join(workflow['output_dir'], 'nextflow.log'),
			'run',
			workflow['pipeline'],
			'-ansi-log', 'false',
			'-latest','1',
			'-with-report','results/report.html',
			'-with-trace','results/trace.txt',
			'-name', run_name,
			'-profile', workflow['profiles'],
			'-revision', workflow['revision'],
			'-with-docker' if workflow['with_container'] else ''
		]

		if resume:
			args.append('-resume')

		with open(run_script, 'a') as f:
			f.write('#!/bin/bash \n')
			run_commands = " " 
			f.write(run_commands.join(args))


		# args = [
		# 	'sbatch',
		# 	run_name+'.sh'
		# ]
		


	

	proc = subprocess.Popen(
		args,
		stdout=open('.workflow.log', 'w'),
		stderr=subprocess.STDOUT
	)

	# return to original directory
	os.chdir(prev_dir)

	return proc



def save_output(workflow, output_dir):
	return subprocess.Popen(
		['./scripts/kube-save.sh', workflow['_id'], output_dir],
		stdout=subprocess.PIPE,
		stderr=subprocess.STDOUT
	)



async def set_property(db, workflow, key, value):
	workflow[key] = value
	await db.workflow_update(workflow['_id'], workflow)



async def launch_async(db, workflow, resume):
	# re-initialize database backend
	db.initialize()

	# start workflow
	work_dir = os.path.join(env.WORKFLOWS_DIR, workflow['_id'])
	proc = run_workflow(workflow, work_dir, resume)
	proc_pid = proc.pid

	print('%d: saving workflow pid...' % (proc_pid))

	# save workflow pid
	await set_property(db, workflow, 'pid', proc.pid)

	print('%d: waiting for workflow to finish...' % (proc_pid))

	# wait for workflow to complete
	if proc.wait() == 0:
		print('%d: workflow completed' % (proc_pid))
		await set_property(db, workflow, 'status', 'completed')
	else:
		print('%d: workflow failed' % (proc_pid))
		await set_property(db, workflow, 'status', 'failed')
		return

	print('%d: saving output data...' % (proc_pid))

	# save output data
	output_dir = os.path.join(env.WORKFLOWS_DIR, workflow['_id'], workflow['output_dir'])
	proc = save_output(workflow, output_dir)

	proc_out, _ = proc.communicate()
	print(proc_out.decode('utf-8'))

	if proc.wait() == 0:
		print('%d: save output data completed' % (proc_pid))
	else:
		print('%d: save output data failed' % (proc_pid))



def launch(db, workflow, resume):
	asyncio.run(launch_async(db, workflow, resume))
