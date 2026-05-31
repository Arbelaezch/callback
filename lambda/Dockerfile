# Dockerfile — callback-submit-application Lambda
#
# Uses Microsoft's official Playwright base image (Ubuntu Noble) which ships
# with Chromium and all system dependencies pre-installed. We layer the
# AWS Lambda Runtime Interface Client (awslambdaric) on top so AWS can
# invoke the container as a Lambda function.
#
# Why not the AWS Lambda Python base image?
# -----------------------------------------
# The AWS Lambda base image is Amazon Linux. Playwright's Chromium binaries
# depend on Ubuntu/Debian system libraries that aren't present on Amazon Linux,
# making it significantly harder to get a working browser. The Playwright base
# image is the path of least resistance.
#
# Image size: ~2GB (Chromium is large). Stored in ECR — Lambda pulls from there.
# Lambda memory: set to 2048MB minimum in AWS console (browser is hungry).
# Lambda timeout: set to 900s (15 min) in AWS console.

FROM mcr.microsoft.com/playwright/python:v1.52.0-noble

# Install the AWS Lambda Runtime Interface Client.
# This is what lets a non-AWS base image act as a Lambda function container.
RUN pip install --no-cache-dir awslambdaric

# Install application dependencies.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright's Chromium browser inside the container.
# (The base image ships the system deps; this adds the browser binary itself.)
RUN playwright install chromium

# Copy handler.
COPY handler.py ${LAMBDA_TASK_ROOT}/handler.py

# Lambda entry point: file.function
CMD ["handler.handler"]