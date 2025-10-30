# RS RoomBot Application!

It sweeps, it mops. It swaps rooms for a few hundred guests at conference style events.
Facilitates participants trading accomodations and answering the critical question of, "where the party at".

![alt text](samples/roombot.png?raw=true)

The RoomBot service allows guests to view which rooms they are assigned, and issue swap requests with other users. A lazy (time-boxed and out of band from this service) authentication process is used to validate room transfers. Some administrative functionality is available primarily in the form of reports.

# Built With

* Django is good at managing relations and providing an api for controlling models. Used for the Room and Guest API model.
* React is good at consuming stuffs and making things look good while they flossing.

# Quickstart

Additional details on these steps are available in this document.

* Contact an adult to request the contents of the "secret file". Put these contents into the `.secret` file in your local working copy.

## Local Development

Docker should be available, and there are several system packages which must be installed (see [Requirements](#Requirements) section below).

```sh
# in one terminal - start the backend
$ make local_backend_dev
# in another terminal
$ make frontend_dev  # start the frontend
# in yet another terminal
$ make sample_data
```

At this point, the local environment will be live at `http://localhost:3000/` and login with one of the sample credentials from [`exampleMainStaffList.csv`](samples/exampleMainStaffList.csv). The example guest lists can now be uploaded at `http://localhost:3000/admin/`.

## AWS Deployment

These instructions are for staging, however production is quite similar. Terraform is used to manage the infrastructure, and the `roombaht_ctl` is used to interact with the deployed host, including deploying build archives.

```sh
$ cd terraform
$ terraform plan
# review for unexpected changes. if this is start of the season, rds and staging
#   and assorted policies and dns should be marked for creation
$ terraform apply -auto-approve
# we only use the "ubuntu" user on first run
$ ./scripts/roombaht_ctl ubuntu staging provision
$ make archive
$ ./scripts/roombaht_ctl my_user staging deploy
```

The next set of commands will depend on which environment you are using. For this example, we will be loading sample data into staging.

```sh
$ ./scripts/roombaht_ctl my_user staging load_staff samples/exampleMainStaffList.csv
$ ./scripts/roombaht_ctl my_user staging load_rooms ballys samples/exampleBallysRoomList.csv
$ ./scripts/roombaht_ctl my_user staging load_rooms nugget samples/exampleNuggetRoomList.csv
```

At this point, the interface will be live, and admins may upload (sample) guest lists.

# Environment / Configuration

Configuration is handled through environment variables, which are stored encrypted in GitHub. Secret management is handled through the `./scripts/secrets` script. You must have a file named `.secret` in the top level of the Git repository. Contact an adult for the contents of this file. See below for full list of configurable settings.

* `./scripts/secrets decrypt <env>` generate the `<env>.env` file from encrypted source
* `./scripts/secrets encrypt <env>` encrypt the `<env>.env` file
* `./scripts/secrets show <env>` display all the env vars in a format suitable for `eval`
* `./scripts/secrets show <env> VAR` display the contents of the desired env var, stripped of quotes

# Local Development

## Requirements

* `make` (a classic)
* Docker configured in a way that networking and local file access works
* Minimum of Python 3.10 with `virtualenv` and `uv`
* A variety of "system packages" (note package names may vary on non-Linux)
  * `build-essential`
  * `imagemagick`
  * `libpq-dev`
  * `python3-dev`
* no not believin' in yo self

## Frontend

This will compile the frontend and run a local server on port `3000`.

```sh
$ make frontend_dev
```

This should build a docker image, use it to generate the react static, and then start react in dev mode listening on port 3000.

## Backend

To configure and run the local development server, simply invoke the `local_backend_dev` target. This will ensure you have a properly configured virtualenv, load the default [dev configuration](https://github.com/Index01/RoomBot/blob/main/dev.env), run migrations, and start the server. If it works, you will have an API server running on port `8000`.

```sh
$ make local_backend_dev
```

You may (optionally) specify a different configuration file when testing locally. This can be done by setting `ROOMBAHT_CONFIG` to the full path of a configuration file.

```sh
$ ROOMBAHT_CONFIG=/path/to/my/special.env make local_backend_dev
```

 As part of the startup, the full configuration will be shown, so you can confirm the right file was loaded.

## Local Data Management

Local development also requires sample data. You may rapidly get up and running by leveraging our sample data. This will leverage a variety of the django management commands (see below). Sample data may be initially loaded via the `sample_data` make target. Local data may otherwise be interacted with via the djano management interface.

To get a guest password, you can use a Django management command. First, already have a running backend.
```sh
$ python backend/manage.py user_show name@noop.com
User Foo Bar, otp: SomeOtp, last login: never
    rooms: 305, tickets: aaa001, onboarding sent: yes
```

# Infrastructure

## AWS

The system is hosted in AWS and is managed via [terraform](https://developer.hashicorp.com/terraform). Please contact an adult for an AWS account and access to the EC2 ssh key. Any reasonably recent version of terraform will probably be fine. There are only three variables that should need changing. The `ami_id` cariable can be used to explicitly set a base AMI, and `postgres_version` is used to set the version installed in RDS. The `staging` and `production` variables can be set to `true` or `false` and control the existence of that environment. The RDS instance will be created if at least one of these is present, and removed if none of them are present.

Begin an infrastructure update by issuing a Terraform "plan". This will provide an indication of what is expected to change. Terraform should only issue changes to resources which have been modified in `.tf` files, along with any dependencies of those resources. Note that resources _may_ change outside of Terraform - installed PostgreSQL version in RDS is one example. When these are encountered, update the version in `meta.tf`.

```sh
$ cd terraform
$ terraform plan
```

If there is nothing unexpected being reported, the `apply` command is used to make the changes. You will be asked to confirm, based on a new plan.

```sh
$ terraform apply
```

## Initial / Baseline Host Configuration

Provisioning a deployed must occur before any other interactions. The `provision` functionality expects the existence of Ubuntu 20.04 server edition. This script is to be run when a host is first created and when any baseline non-application changes are desired. It will execute [`./scripts/provision-remote.sh`](https://github.com/Index01/RoomBot/blob/main/scripts/provision-remote.sh) on the remote host. Note that the _first_ time this command is run, the `ubuntu` user must be used, and the EC2 ssh private key must be available. All subsequent interactions with the deployed host must be through a normal user. SSH keys for users are pulled from GitHub.

```sh
$ `./scripts/roombaht_ctl ubuntu <env> provision
```

# Managing a Real Host

There are a variety of scripts used for managing either the production (`prod`) or staging/dev (`staging`) environments. Please contact an adult for information on SSH access, hostnames, and the location of a perfect dry martini. May of these commands are accessed via the `roombaht_ctl` script, which provides a commmon execution interface.

```sh
$ ./scripts/roombaht_ctl <user> <env> <command> <arg1> <arg2> ....
```

## Deployment

The `deploy` script will handle deployment to either the production (`prod`) or staging/dev (`staging`) environments. It handles the creation of artifacts, shipping and installing the artifacts, and configuring the remote host, database migrations, and other things needed for a running `roombaht` instance. The deployment script will ask for manual confirmation if you are deploying from a branch other than `main` or if the local git repository is dirty. You may bypass the confirmation by passing the `-f` option. But you shouldn't. You must locally build artifacts prior to deployment.

```sh
$ make archive
$ ./scripts/deploy <user> <env>
```

You may optionally execute a "quick" deployment. This skips the management of the virtualenv, database migrations, and the nginx configuration. Good for emergency fixes. Use with care. This may only be done after a "full" deployment has succesfully completed.

```sh
$ ./scripts/deploy <user> <env> -q
# shit's on fire yo and i just want to ship a code fix
$ ./scripts/deploy <user> <env> -q -f
```

## Logs

There are shortcut commands which allow for easy viewing of backend (`roombaht` uwsgi / `roombaht` out-of-band) and frontend (`nginx` access and error) logs. These commands are accessed via `roombaht_ctl`.

```sh
$ ./scripts/roombaht_ctl <user> <env> backend-logs
$ ./scripts/roombaht_ctl <user> <env> frontend-logs
```

## Data Management

Managing data on remote hosts is a whole _thing_. Please read this section carefully and make sure to leverage the DB Snapshot functionality (see below) for risky operations.

### Data Population

These commands will populate the database with both sets of hotel files and the initial staff. Use caution when loading the same rooms over and over. Ask an adult before running this outside of staging.

```sh
./scripts/roombaht_ctl <user> <env> load_staff /path/to/staff.csv
./scripts/roombaht_ctl <user> <env> load_rooms ballys /path/to/ballys.csv
./scripts/roombaht_ctl <user> <env> load_rooms nugget /path/to/nugget.csv
```

### Room Creation / Updating

You can directly invoke `create_rooms` using the `manage` shortcut.

When updating you may also execute a dry run to verify changes. Note that when updating, every change requires a manual confirmation. You may bypass this with `--force` but you probably should not. Additional logging is available via `--debug`. View all options with `--help`

```sh
# view help
$ ./scripts/roombaht_ctl <user> <env> manage create_rooms --help
# create initial room set
$ ./scripts/roombaht_ctl <user> <env> manage create_rooms /path/to/ballys-rooms.csv --hotel ballys
# check for changes
$ ./scripts/roombaht_ctl <user> <env> manage create_rooms /path/to/ballys-rooms.csv --hotel ballys --preserve --dry-run
# actually apply the changes. user input will be required for all changes.
$ ./scripts/roombaht_ctl <user> <env> manage create_rooms /path/to/ballys-rooms.csv --hotel ballys --preserve
```

### Random (admin) Room Assignment

The `test_fill_rooms` Django command will assign rooms to admins at random, approximately simualting how rooms are assigned based on Secret Party exports. By default, only five rooms will be assigned per admin.

This command will _not_ run in production, and requires a manual confirmation in staging.

## Images

Images are kinda like data? There is a script that will either work based on an existing downloaded folder (i.e. if you have GDrive setup on a computer) or will attempt to use `gdown` to fetch the folder magially. It will then generate thumbnails and put the images in the right place. Not these images will _not_ end up in the git repo. Images will be fetched during the `frontend_build` step if they are not present.

```
./scripts/fetch-images
./scripts/fetch-images /path/to/gdrive/images
```

## Data Sanitization

There is a script which will take live data from the room list spreadsheet and a Secret Party export and appropriately anonymize it. For the room list, some randomness may be applied, and there are configurable weights. All guests and placers listed in the room list will be sourced from the original room list.

For the guest list, the following changes are made

* The first and last name are changed
* The email is changed
  * Duplicate emails (per name) are mapped down to a single email
* Transfer to / from is mapped to the appropriate names
* Phone number is randomly generated per name

For the room list, the following changes are made

* The first and last name are changed.
  * Secondary names, if present, are also changed
* Placers (art and manual room) are selected from a randomly generated group.
* All blank `Placed By` fields are replaced with `Roombaht`
* Optionally, placed rooms may be randomly generated, ignoring original selections (weight name `placed`, default 10%).
* Optionally, secondary names may be randomly added to placed rooms (weight name `secondary`, default 50%).
* Art room types are always selected from a randomly generated group.
* Optionally, a random selection of rooms will become art rooms (weight name `art`, default 5%).
* Optionally, placed rooms have a chance to be set as changable (weight name `changeable`, default 50%)

```
python ./backend/scripts/massage_csv.py /tmp/SecretPartyExport.csv /tmp/RoomsSheetExport.csv --weight placed:30,art:10
```

## Database Manipulation

There are three commands which allow for wiping, creating snapshots, and cloning either production or a specific database. These commands are accessed via `roombaht_ctl`.

### Wipe

This command will fully wipe (via drop / create) the database for the specified environment. Migrations will need to be performed after this so it should be followed by a deployment. Note it is super annoying (if actually possible, under certain circumstances) to undo. So be careful.

```sh
$ ./scripts/roombaht_ctl <user> <env> wipe
```

### Snapshot

This command will create a new database using the specified environment as a template. The naming format will be `<ROOMBAHT_DB>-MMDDYYYY-HHMM`.

```sh
./scripts/roombaht_ctl <user> <env> snapshot
```

### Clone

This command is super helpful for testing in staging. It will create a new database, using either production on a specified database as the template. Note this can _only_ be run on staging.

```sh
# clone production
./scripts/roombaht_ctl <user> <env> clone
# clone the production snapshot from a funny date and time
./scripts/roombaht_ctl <user> <env> -d roombaht-010169_1620
```

## Django Management Commands

There are a variety of django management commands, both stock and custom, which are accessible on the deployed hosts. These commands may be accessed via `roombaht_ctl`. All of these commands take a `--help` option for available options/arguments. And you can issue the `help` command for a list of commands Note that several of these commands are meant to be accessed directly via `roombaht_ctl` commands in order to handle things like copying files and user confirmation.

```sh
$ ./scripts/roombaht_ctl <user> <env> manage help
```

### Guest Management

Some information may be viewed and some changes may be made for guests.

* `./scripts/roombaht_ctl <user> <env> manage user_show --help` allows viewing guests based on email address, name, ticket, or transfer.
* `./scripts/roombaht_ctl <user> <env> manage user_edit --help` allows limited editing of guests.

### Room Management

Some information may be viewed and some changes may be made for rooms.

There are two scripts to be used for modifying deployed hosts. They each take two arguments; a SSH username and remote host. Ask an adult for your SSH username and the remote host name.

* `./scripts/roombaht_ctl <user> <env> manage room_list --help` will display a listing of rooms with some metadata. Helpful for dev / debugging.
* `./scripts/roombaht_ctl <user> <env> manage room_show --help` will display information on a room.
* `./scripts/roombaht_ctl <user> <env> manage room_edit --help` allows editing of a variety of room information.
* `./scripts/roombaht_ctl <user> <env> manage fix_room --help` will display, and optionally fix, detectable data corruption issues on a room.
* `./scripts/roombaht_ctl <user> <env> manage room_swap --help` will manually swap rooms. It has the same restrictions that are placed on user-initiated room swaps.

### Shell

Sometimes you just want to muck around with a interactive Python interpreter that has access to the entire set of `roombaht` modules. This command will invoke the django shell.

```sh
$ ./scripts/roombaht_ctl <user> <env> manage shell
```

# Configuration Settings

The `ROOMBAHT_DB_HOST` and `ROOMBAHT_DB_PASSWORD` configuration variables are only used in AWS environments, and they are automatically determined based on the RDS deployment.

* `ROOMBAHT_DEV` Should be set to `true` on dev and never on prod. Controls DB usage and enables some local dev functionality. Defaults to `false`.
* `ROOMBAHT_DEV_MAIL` if this is set to an email address then any address for the `@noop.com` domain will be converted to be a prefix email. Example `foo@gmail.com` and `bar@noop.com` would convert to `foo+bar@gmail.com`. Helpful for testing room swaps. Defaults to disabled.
* `ROOMBAHT_SEND_MAIL` Needs to be set to `true` for email to be sent. Defaults to `false`.
* `ROOMBAHT_SEND_ONBOARDING` Needs to be set to `true` for the onboarding emails to be sent during Secret Party export ingestion. Defaults to `false`.
* `ROOMBAHT_LOGLEVEL` Controls the Python log level. Should be set to one of `ERROR`, `WARNING`, `INFO`, `DEBUG`. Defaults to `INFO` on prod and `DEBUG` on dev.
* `ROOMBAHT_HOST` is the hostname part of the url to be used when generating our url in emails and wherever else. Defaults to `localhost`.
* `ROOMBAHT_PORT` is the port part of the url to be used when generating our url in emails and wherever else. Defaults to `80`.
* `ROOMBAHT_SCHEMA` is the schema part of the url. Defaults to `http`.
* `ROOMBAHT_TMP` is where we yeet temporary files. Defaults to `/tmp`.
* `ROOMBAHT_IGNORE_TRANSACTIONS` This is a CSV list of transactionts to not care about.
* `ROOMBAHT_JWT_KEY` is basically the salt for o ur auth tokens. This must be set, there is no default.
* `ROOMBAHT_DJANGO_SECRET_KEY` Might not even be used since we don't use Django sessions?
* `ROOMBAHT_EMAIL_HOST_USER` This is the SMTP user and it must be set, there is no default.
* `ROOMBAHT_EMAIL_HOST_PASSWORD` This is the SMTP password and it must be set, there is no default.
* `ROOMBAHT_SWAPS_ENABLED` Is a boolean which controls whether swaps are enabled or not. Defaults to `True`.
* `ROOMBAHT_GUEST_HOTELS` Is a CSV list of hotel names that will be processed during guest ingestion. Defaults to `Ballys`.

# DB Schema

## Guest

Tracks every guest. Every guest the system is aware of will have a room associated.

* `name` The full name of a registered guest.
* `email` The email of a guest. Ued for login.
* `ticket` The Secret Party ticket ID.
* `invitation` The Secret Party invitation ID.
* `jwt` The (per user) magical token of hope and wonder and access.
* `room_number` The room a guest is located in.

## Staff

Staff can do staff like things.

* `name` The short name / alias for the staff.
* `email` The email address for the staff.
* `is_admin` A boolean that may or may not be set to true.
* `guest` A mapping to a guest record.

## Room

Rooms are where the party is.

* `number` The room number.
* `name_take3` The internal name for the room. What a user will see.
* `name_hotel` The hotel room name.
* `is_available` Whether or not the room is in any way available.
* `is_swappable` Whether or not the room is swappable. Must also be available.
* `is_smoking` Is it a smoking room? Maps from room features.
* `is_lakeview` Is it a lake view room? Maps from room features.
* `is_ada` Is it an accessible room? Maps from room features.
* `is_hearing_accessible` Is the room hearing accessible i.e. does it have visual indicators for alarm conditions. Maps from room features.
* `swap_code` The code used for swapping a room.
* `swap_time` The date and time of when the room was swapped.
* `check_in` The check in date.
* `check_out` The check out date.
* `notes` General notes about the room.
* `guest_notes` Rooms specific to the guest in the room.
* `sp_ticket_id` The Secret Party ticket ID.
* `primary` The full name of the primary resident in the room.
* `secondary` The full name of a secondary person in the room.
* `placed_by_roombot` Indicates that this is a room which can be placed by roombot. Implies not a placed room.
* `guest` A mapping to a guest record.
