
FROM python:3.11

ENV PATH /usr/local/bin:$PATH

ENV PYTHONUNBUFFERED 1

RUN mkdir /app
COPY /src /app
WORKDIR /app

RUN curl -LO https://storage.googleapis.com/kubernetes-release/release/$(curl -s https://storage.googleapis.com/kubernetes-release/release/stable.txt)/bin/linux/amd64/kubectl
RUN chmod +x ./kubectl
RUN mv ./kubectl /usr/local/bin
RUN pip3 install -r requirements.txt

CMD ["python", "main.py"]