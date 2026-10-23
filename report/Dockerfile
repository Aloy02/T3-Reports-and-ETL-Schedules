FROM public.ecr.aws/lambda/python:3.14

# Copy requirements file into Lambda task root
COPY generator/requirements.txt ${LAMBDA_TASK_ROOT}/requirements.txt


RUN pip install --no-cache-dir -r ${LAMBDA_TASK_ROOT}/requirements.txt

# Copy application code
COPY generator/ ${LAMBDA_TASK_ROOT}/

# Specify handler execution target
CMD [ "create_report.lambda_handler" ]