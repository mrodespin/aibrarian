
# /api/Dockerfile

# 1. Use an official lightweight Python image
FROM python:3.11-slim

# 2. Set the working directory inside the container
WORKDIR /app

# 3. Copy requirements file first (for caching)
COPY requirements.txt .

# 4. Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# 5. Copy the rest of the application code
# It copies the local './app' folder into the container's '/app/app' folder
COPY ./app /app/app

# 6. Expose the port the API will run on
EXPOSE 8000

# 7. Command to run the application (will be run by docker-compose, or by
# Render with $PORT set to whatever port it assigns — defaults to 8000
# for local/docker-compose use where PORT isn't set).
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]