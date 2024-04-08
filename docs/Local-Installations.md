# Local Installations

* Requires `python 3.8.1`. Dependencies must be installed by running:

Navigate to the directory you'd liked to clone the repo into

Clone the repo

```bash
git clone https://github.com/StuffAnThings/qbit_manage
```

Install requirements

```bash
pip install -r requirements.txt
```

If there are issues installing dependencies try:

```bash
pip install -r requirements.txt --ignore-installed
```

## Usage

To run the script in an interactive terminal run:

* copy the `config.yml.sample` file to `config.yml`
* Fill out the config file as outlined in the [Config-Setup](https://github.com/StuffAnThings/qbit_manage/wiki/Config-Setup)

Run the script `-h` to see a list of commands

```bash
python qbit_manage.py -h
```

### Config

To choose the location of the YAML config file

```bash
python qbit_manage.py --config-file <path_to_config>
```

### Log

To choose the location of the Log File

```bash
python qbit_manage.py --log-file <path_to_log>
```
