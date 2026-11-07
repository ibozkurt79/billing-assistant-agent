FROM python:3.13-slim

WORKDIR /app

# Install dependencies first: this layer is cached until requirements.txt changes
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Then copy the code
COPY . .

CMD ["python", "main.py"]