FROM apache/airflow:2.7.1

USER root

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    libssl-dev \
    libffi-dev \
    default-jdk \
    git \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

    # Java_home
ENV JAVA_HOME=/usr/lib/jvm/java-11-openjdk-amd64

# Set default UID if not specified
#ENV AIRFLOW_UID=${AIRFLOW_UID:-1000}

# Modify the airflow user to have the specified UID and root group
RUN usermod -u 1000 airflow && \
    usermod -g 0 airflow

# Create required directories
RUN mkdir -p /opt/airflow/dags /opt/airflow/plugins /opt/airflow/logs /opt/airflow/data \
    && chown -R airflow /opt/airflow  && chmod -R 775 /opt/airflow


USER airflow
# Install Python dependencies - specify your actual requirements
COPY requirements.txt /requirements.txt
RUN pip install --no-cache-dir -r /requirements.txt
