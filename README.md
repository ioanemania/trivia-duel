
# Trivia Duel

A multiplayer game of trivia that lets you play against another player.

- [Features](#features)
- [How to run and play the game](#how-to-run-and-play-the-game)
- [Overview](#a-brief-overview)
- [How to run tests](#how-to-run-tests)

## Features

- Ranked and unranked multiplayer games
- Leaderboards
- Game History
- Training mode

## How to run and play the game

To play the game we need to connect to a running trivia-duel server with the
trivia-duel client.

To start the server:

first build and run migrations: `docker compose run app python manage.py migrate`

then start the server using: `docker compose up app`

And to run the client also use docker compose:

`docker compose run client`

Running `docker compose run client` will connect to the default server in
docker compose, you can also specify the server location manually:

```
$ docker compose run client -h

usage: main.py [-h] [server_location]

Duel other players in multiplayer trivia games!

positional arguments:
  server_location  hostname and port of the server (default: app:8000)

options:
  -h, --help       show this help message and exit
```

So for example: `docker compose run client localhost:8000`

NOTE! You can use the `escape` key to get back to the previous menu!

## A brief overview

The project is separated into two components:

- The server
- The client

The server is a django application to which the clients are supposed to connect
to in order to play.

The client is a text-based user interface (TUI) application built using the
[textual](https://github.com/Textualize/textual) framework.

Trivia questions are obtained from the [Open Trivia Database
API](https://opentdb.com/api_config.php).

The multiplayer game modes are implemented using websockets.

Architecture of the server is simple, it consists of:

- The django application
- a postgresql database
- and a redis database

The django application uses django-rest-framework and django-channels to
provide API endpoints and a websocket consumer.

The `GameConsumer` websocket consumer is the core of how the multiplayer games
work: clients connect to the `GameConsumer` and exchange certain events with
the server to play out a game.

All of the other features are simple API endpoints provided by the django
application.

## How to run tests

To run the server tests:

`docker compose run app-test python manage.py test`

To run the client tests:

`docker compose run --entrypoint python client test.py`
