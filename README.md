[![Maintenance](https://img.shields.io/badge/Maintained%3F-yes-green.svg)](https://GitHub.com/DavidPL1/Hyperion/graphs/commit-activity)
[![GPLv3 license](https://img.shields.io/badge/License-GPLv3-blue.svg)](http://perso.crans.org/besson/LICENSE.html)

# Hyperion

## What is Hyperion

Hyperion is an engine designed to launch and monitor user defined components using YAML configuration files.
Inspired by [vdemo](https://code.cor-lab.org/projects/vdemo) and [TMuLE](https://github.com/marc-hanheide/TMuLE) (see [vdemo and TMuLE assessment](/DavidPL1/Hyperion/wiki/vdemo-and-TMuLE-assessment))

## How does it work

Hyperion (like TMuLE) is written in Python and utilizes the [tmux library for python](https://github.com/tmux-python/libtmux) to start components in detached sessions. For each host defined in the components a master session is created, in which each component will be started in a window. Components are managed by a main server that delegates commands to slave server instances on remote machines and forwards information to subscribed user interfaces.

## Installation

The Hyperion core package can be installed via setuptools `python setup.py install` or via pip `pip install .`
Installing with catkin is now also supported on the master branch.

To enable dependency graph visualisation, you need to install the [graph visualisation extension](https://github.com/hyperion-start/hyperion-graph-visualisation)

If you want to use the interactive cli based on urwid, you need to install the [user interfaces extension](https://github.com/hyperion-start/hyperion-ui).

If you wish to use the PyQt gui, additionally to the ui extension Qt4 for python has to be installed via a package manager (`apt install python-qt4` on debian based distributions). This is due to the fact, that the PyQt4 package can not be managed by pip. Hyperion is able to detect if PyQt4 is installed at runtime and if so enable the GUI features.

## Quick Guide

Hyperion supports various modes:

### Server mode [CORE]

```
usage: hyperion server --config CONFIG [-h] [-p PORT]

optional arguments:
  -h, --help            show this help message and exit
  -p PORT, --port PORT  Define the TCP port on which the backend will listen
                        for clients. Default: 23081
```

Server mode starts a component manager as master that listens for clients on the specified port (if none is given defaults to 23081) and connects to remote machines starting slave instances. Clients can connect to the server to issue commands or request information from the manager.

### Execute mode [CORE]

```
usage: hyperion execute --config CONFIG [-h] { -l | ([-C COMP [COMP ...]] ( -s | -k | -c | -L | -T))}

optional arguments:
  -h, --help            show this help message and exit
  -C COMP [COMP ...], --component COMP [COMP ...]
                        single component or list of a components
  -l, --list            List all available components
  -s, --start           start the component
  -k, --stop            Stop the component
  -c, --check           Check the component
  -L, --log             Show the component log
  -T, --term            Show the component term
```

The execute mode will initialize the configured system with the executing host as controlling instance. It offers to run a specific action for a single component or a list of components and exit.

### UI mode (WORK IN PROGRESS)

```
usage: hyperion ui [-h] [-p PORT] [-H HOST | --no-socket] [-x]

optional arguments:
  -h, --help            show this help message and exit
  -p PORT, --port PORT  Specify port to connect to. Defaults to 23081
  -H HOST, --host HOST  Specify host to connect to. Defaults to localhost
  --no-socket           Start in standalone mode without connecting to a
                        running backend
  -x                    Use PyQt gui (requires X server and python-qt4
                        package)
```

UI mode starts a user interface (PyQt or interactive cli) which either connects to a running hyperion backend or if started in standalone mode runs its own backend. Note that the backend created by standalone mode will terminate when the ui is exited and unlike a backend started by server mode, it will not accept connections from other uis.

Visit [Control GUI](/DavidPL1/Hyperion/wiki/Control-GUI) for detailed information about the GUI.
Visit [Interactive CLI](/DavidPL1/Hyperion/wiki/Interactive-CLI-Mode) for detailed information about the interactive cli.

### Validation mode

```
hyperion validate --config systems/demo.yaml [-h] [--visual]

optional arguments:
  -h, --help  show this help message and exit
  --visual    Generate and show a graph image
```

The validation mode parses the dependencies specified in the component configuration files and checks whether they are all met makes sure the directed dependency graph is acyclic (no circular dependencies) to check if starting all components with their dependencies is possible.
Errors (unmet and circular dependencies) are displayed on the cli.
If the configuration is valid, a list showing the order for a full system start is printed on the cli.

By specifying the visual argument, the command will generate an image of the the dependency graph (highlighting errors). _Please note:_ if a circular dependency error is detected, the graph will be incomplete because the algorithm won't be able to iterate through the remaining nodes!

<p align="center">
  <img src="https://github.com/DavidPL1/Hyperion/wiki/img/depgraph_1-122018.png?raw=true" alt="Graph generated with the sample components with missing dependency error (December 2018)"/>
</p>

**_Image:_** _Graph generated with the sample components with missing dependency error (December 2018)_

<p align="center">
  <img src="https://github.com/DavidPL1/Hyperion/wiki/img/depgraph_2-122018.png?raw=true" alt="Graph generated from intermediate scale robotic simulation system (December 2018)"/>
</p>

**_Image:_** _Graph generated from intermediate scale robotic simulation system (December 2018)_

### Editor mode (NIY)

```
hyperion edit --config systems/demo.yaml
```

The editor mode is planned to provide an editor GUI to create and edit components, groups and systems.
The main idea is, to prevent misconfiguration by syntax errors in the configuration files and to help configure dependencies.
This feature will use the validation mode.

### Slave mode

```
hyperion slave --config CONFIG [-h] -p PORT -H HOST

optional arguments:
  -h, --help            show this help message and exit
  -p PORT, --port PORT  specify port of the master server to connect to
  -H HOST, --host HOST  specify master server hostname to connect to
```

The slave mode launches a limited version of a manager server which immediately connects to a master server on the given host at the given port. It features starting, stopping and checking local components and will forward monitoring events and check results to the master server. Note that the slave mode is not intended to by started by hand, but by a master server.

## Restrictions/Requirements

tmux >= 1.8 is required to handle libtmux's calls.
system config names are not allowed to contain a space!

---

For more information about the developement and upcoming features visit the [wiki](https://github.com/DavidPL1/Hyperion/wiki)
