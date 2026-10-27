# Use an official lightweight Python base image
FROM python:3.11-slim

# Set the working directory inside the container
WORKDIR /app

# Prevent Python from writing .pyc files and enable unbuffered logging
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Install FastAPI and Uvicorn directly (or use a requirements.txt if preferred)
RUN pip install --no-cache-dir fastapi uvicorn

# Copy the application code into the container
COPY main.py .

# Expose the port that FastAPI will run on
EXPOSE 8080

# Command to run the application using uvicorn production settings
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
