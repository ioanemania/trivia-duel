FROM python

ENV TERM xterm-256color

WORKDIR /app

COPY . .

RUN pip install -r requirements.txt

ENTRYPOINT ["python", "main.py"]