#!/usr/bin/python

import beanstalkc
import json
import logging
import os
import subprocess
import constants

import config

config.load_logger()
logger = logging.getLogger("linter")


def write_dockerfile(dockerfile):
    if os.path.isdir("/tmp/scan"):
        logger.info("/tmp/scan directory already exists")
    elif os.path.isfile("/tmp/scan"):
        os.remove("/tmp/scan")
        os.makedirs("/tmp/scan")
    else:
        os.makedirs("/tmp/scan")

    with open("/tmp/scan/Dockerfile", "w") as f:
        f.write(dockerfile)


def export_linter_logs(logs_file_path, data):
    """
    Export linter logs in given directory
    """
    try:
        fin = open(logs_file_path, "w")
        fin.write(data)
    except IOError as e:
        logger.log(
            level=logging.CRITICAL,
            msg="Failed to write linter logs on NFS share."
        )
        logger.log(
            level=logging.CRITICAL,
            msg=str(e))
    else:
        logger.log(
            level=logging.INFO,
            msg="Wrote linter logs to log file: %s" % logs_file_path
            )


def export_linter_status(status, status_file_path):
    """
    Export status of linter execution for build in process
    """
    try:
        fin = open(status_file_path, "w")
        json.dump(fin, status)
    except IOError as e:
        logger.log(
            level=logging.CRITICAL,
            msg="Failed to write linter status on NFS share."
        )
        logger.log(
            level=logging.CRITICAL,
            msg=str(e)
        )
    else:
        logger.log(
            level=logging.INFO,
            msg="Wrote linter status to file: %s" % status_file_path
            )


def lint_job_data(job_data):
    """
    Function to orchestrate Dockerfile linter execution
    """
    logger.info("Received job data from tube")
    logger.info("Job data: %s" % job_data)

    dockerfile = job_data.get("dockerfile")

    logger.info("Writing Dockerfile to /tmp/scan/Dockerfile")
    write_dockerfile(dockerfile)

    logger.info("Running Dockerfile Lint check")
    out, err = subprocess.Popen(
        ["docker",
         "run",
         "--rm",
         "-v",
         "/tmp/scan:/root/scan:Z",
         "registry.centos.org/pipeline-images/dockerfile-lint"],
        stdout=subprocess.PIPE
    ).communicate()

    if err is None:
        logger.info("Dockerfile Lint check done. Exporting logs.")
        # logs file for linter
        logs_file_path = os.path.join(
                constants.LOGS_DIR,
                constants.LINTER_RESULTFILE
                )

        # logs URL for linter results
        logs_URL = logs_file_path.replace(
                constants.LOGS_DIR,
                constants.LOGS_URL_BASE
                )
        # linter execution status file path
        status_file_path = os.path.join(
                constants.LOGS_DIR,
                constants.LINTER_STATUS_FILE
                )

        out += "\n\nHosted linter results : %s\n" % logs_URL
        export_linter_logs(logs_file_path, out)

        response = {
            "logs": out,
            "linter_results": True,
            "action": "notify_user",
            "namespace": job_data.get('namespace'),
            "notify_email": job_data.get("notify_email"),
            "job_name": job_data.get("job_name"),
            "msg": None,
            "linter_results_path": logs_file_path,
            "logs_URL": logs_URL,
        }

    else:
        logger.error("Dockerfile Lint check failed", extra={'locals': locals()})
        response = {
            "linter_results": False,
            "action": "notify_user",
            "namespace": job_data.get('namespace'),
            "notify_email": job_data.get("notify_email"),
            "job_name": job_data.get("job_name"),
            "msg": err,
        }

    # now export the status about linter execution in logs dir of the job
    # this response will be read after job builds and sending email to user
    export_linter_status(response, status_file_path)

bs = beanstalkc.Connection(host="BEANSTALK_SERVER")
bs.watch("start_linter")


def main():
    while True:
        try:
            job = bs.reserve()
            job_data = json.loads(job.body)
            lint_job_data(job_data)
            job.delete()
        except Exception as e:
            logger.fatal(e.message, extra={'locals': locals()}, exc_info=True)

if __name__ == '__main__':
    main()
