# Overview
Topics covered in this README:
* Chaos Engineering
* Creating Experiments
* Probes and Actions
* Chaos Environment
  * Installation
  * Configuration
* Executing Experiments

# Chaos Engineering
Chaos Engineering is the discipline of experimenting on a distributed system in
order to build confidence in the system’s capability to withstand turbulent
conditions in production. -- principlesofchaos.org

## Chaostoolkit
“The Chaos Toolkit aims to be the simplest and easiest way to explore building
your own Chaos Engineering Experiments. It also aims to define a vendor and
technology independent way of specifying Chaos Engineering experiments by
providing an Open API.” (https://docs.chaostoolkit.org/)

## chaosindy
A number of actions and probes have been developed to facilitate composing
experiments for Hyperledger Indy. They are currently being maintained here in
the “chaosindy” python module.

When existing “chaosindy” actions and probes need to execute remotely, python
Fabric (not to be confused with Hyperledger Fabric) is used, which is
“designed to execute shell commands remotely over SSH, yielding useful Python
objects in return”.

# Creating Experiments
“An Experiment declares a steady state hypothesis, alongside probes to validate
this steady state is met, and a method as a sequence [of] actions and probes,
to interact and query the system respectively.”
(https://docs.chaostoolkit.org/reference/api/experiment/)

Experiments are declared in JSON files and are composed of the following
elements. Ellipses (...) added for brevity:

* Version
* Title
* Description
* Tags
* Secrets
* Configuration
* Steady State Hypothesis
* Method
* Rollbacks

```
{
    "version": "1.0.0",
    "title": "Force View Change",
    "description": “...”,
    "tags": [...],
    "secrets": {...},
    "configuration": {...},
    "steady-state-hypothesis": {...},
    "method": [...],
    "rollbacks": [...]
}
```
## Version

The version property MUST be "0.1.0". The docs are not clear what the version
number is used for, but we suspect that the ‘chaos’ executable will eventually
need to know the version of API to use to parse/interpret and execute the
experiment.

The current specification has not reached its 1.0.0 stable version yet. Make
sure to join the discussion to provide any feedback you might have.

```
{
    "version": "0.1.0",
    ...
}
```

## Title and Description

The experiment’s title and description are meant for humans and therefore
should be as descriptive as possible to clarify the experiment’s rationale.

```
{
    ...
    "title": "Force View Change",
    "description": “Reach steady state (can write a nym), discover which node is the master, stop the master (stop indy-node service) on that node to force a view change, wait a reasonable amount of time for the view change to complete, verify another node has been selected as the new master, bring up the old master, and then ensure the cluster is still in consensus (can write a nym). This experiment can be repeated to 'chase the master'.
”,
    ...
}
```

## Tags

Tags provide a way of categorizing experiments. It is a sequence of JSON
strings.

```
{
    ...
    "tags": [
        "service",
        "indy-node",
        "consensus"
    ],
    ...
}
```

## Secrets
Secrets declare values that need to be passed on to Actions or Probes in a
secure manner.

Secrets may be inlined, passed via the environment, or retrieved from a
HashiCorp vault instance.

```
{
    ...
    "secrets": {
        "sovrin": {
            "seed": “0000000000000000000000000Trustee1”,
            "env-seed": {
                “type”: “env”,
                “key”: “CHAOS_SEED”
            },
            "vault-seed": {
                “type”: “vault”,
                “key”: “chaos/seed”
            }
        }
    },
    ...
}
```

## Configuration
Configuration is meant to provide runtime values to actions and probes.

```
{
    ...
    "configuration": {
        "genesis_file": {
            "type": "env",
            "key": "CHAOS_GENESIS_FILE"
        },
        "write_nym_timeout": {
            "type": "env",
            "key": "CHAOS_WRITE_NYM_TIMEOUT"
        },
       "cleanup": {
            "type": "env",
            "key": "CHAOS_CLEANUP"
        }
    },
    ...
}
```

## Steady State Hypothesis
The Steady State Hypothesis element describes what normal looks like in your
system before the Method element is applied. If the steady state is not met, the
Method element is not applied and the experiment MUST bail out.

The Steady State Hypothesis is checked before and after the Method element is
applied, is entirely composed of one or more probes with a “tolerance” element
(predicate) acting as a gate mechanism.

```
{
    ...
    "steady-state-hypothesis": {
        "title": "Can write nym",
        "probes": [
            {
                "type": "probe",
                "name": "can-write-nym",
                "tolerance": true,
                "provider": {
                    "type": "python",
                    "module": "chaosindy.probes.write_nym",
                    "func": "write_nym",
                    "arguments": {
                        "seed": "${seed}",
                        "genesis_file": "${genesis_file}",
                        "pool_name": "fvc_pool1",
                        "my_wallet_name": "fvc_my_wallet1",
                        "their_wallet_name": "fvc_their_wallet1",
                        "timeout": "${write_nym_timeout}"
                    }
                }
            }
        ]
    },

    ...
}
```

## Method
The Method describes the ordered sequence of Probe and Action elements to apply.

The “stop-primary” and “start-stopped-primary-after-view-change” actions could
be combined into a “force-view-change” action.

Composition can be done in the experiment or in the modules (probe, action
modules).

```
{
    ...
    "method": [{
        "type": "action",
        "name": "stop-primary",
        "provider": {
            "type": "python",
            "module": "chaosindy.actions.primary",
            "func": "stop_primary",
            "arguments": {
                "genesis_file": "${genesis_file}"
            }
        }
    },{
        "type": "action",
        "name": " start-stopped-primary-after-view-change",
        "provider": {
            "type": "python",
            "module": "chaosindy.actions.primary",
            "func": "start_stopped_primary_after_view_change",
            "arguments": {
                "genesis_file": "${genesis_file}"
            }
        }
    }],
    ...
}
```

## Rollbacks
Rollbacks declare the sequence of actions that attempt to put the system back to
its initial state.

Rollbacks are called regardless of what happens during Method execution. If all
probes/actions execute w/o problems, rollbacks are executed. If one or more
probes/actions stacktrace, rollbacks are executed.

Rollbacks are like the “finally” clause in a try...except...finally block.

```
{
    ...
    "rollbacks": [
        {
            "type": "action",
            "name": "start-stopped-primary",
            "provider": {
                "type": "python",
                "module": "chaosindy.actions.primary",
                "func": "start_stopped_primary",
                "arguments": {
                    "genesis_file": "${genesis_file}"
                }
            }
        },
        {
            "type": "action",
            "name": "cleanup-validator-info",
            "provider": {
                "type": "python",
                "module": "chaosindy.actions.validator_info",
                "func": "delete_validator_info",
                "arguments": {
                    "cleanup": "${cleanup}"
                }
            }
        }
    ],
    ...
}
```

# Probes and Actions
A Probe collects information from the system during the Steady State Hypothesis,
or Method phases of an experiment.

An Action collects information and/or performs an operation against the system
(i.e. stop-master, or start-stopped-master) during the Method and Rollback
phases of an experiment.

The Steady State Hypothesis phase is executed before and after the Method phase.
It is a sequence of Probes that declare an additional property named
“tolerance”. The tolerance is a condition/predicate that must be true for the
experiment to succeed/pass. If a Probe is used in the Method of an experiment,
the tolerance is checked/evaluated, but will NOT cause the experiment to fail.

The Method phase is a sequence of Probes and Actions.

The Rollback phase is a sequence of Actions.

## Probe
When declared fully, a Probe MUST declare:
* type property
* name property
* provider property

The type property MUST be the JSON string "probe".

The name property is a free-form JSON string that MAY be considered as an
identifier within the experiment.

It MAY also declare:
* secret property
* configuration property
* background property - MUST not block and the next Action or Probe should
  immediately be applied. Default: false

```
{
    "type": "probe",
    "name": "can-write-nym",
    "tolerance": true,
    "provider": {
        "type": "python",
        "module": "chaosindy.probes.write_nym",
        "func": "write_nym",
        "arguments": {
            "seed": "${seed}",
            "genesis_file": "${genesis_file}",
            "pool_name": "fvc_pool1",
            "my_wallet_name": "fvc_my_wallet1",
            "their_wallet_name": "fvc_their_wallet1",
            "timeout": "${write_nym_timeout}"
        }
    },
    “background”: false
}
```

## Action
When declared fully, a Action MUST declare:
* type property
* name property
* provider property
The type property MUST be the JSON string "action".
The name property is a free-form JSON string that MAY be considered as an
identifier within the experiment.
It MAY also declare:
* secret property
* configuration property
* background property
* pauses property - number indicating the number of seconds to wait before
  continuing

```
{
    "type": "action",
    "name": "stop-primary",
    "provider": {
	"type": "python",
	"module": "chaosindy.actions.primary",
	"func": "stop_primary",
	"arguments": {
	    "genesis_file": "${genesis_file}"
	}
    }
}
```

# Chaos Environment - Install and Config
## Installation
Setup and configure the chaosindy project on a client node.
### Clone chaosindy repo:
```
ubuntu@client1:~$ git clone https://github.com/evernym/chaosindy.git
ubuntu@client1:~$ cd chaosindy
```
### Install chaostoolkit inside a python virtual environment:
```ubuntu@client1:~$ sudo apt-get install python3 python3-venv libffi-dev
ubuntu@client1:~$ python3 -m venv ~/.venvs/chaostk
ubuntu@client1:~$ source  ~/.venvs/chaostk/bin/activate
(chaostk) ubuntu@client1:~$
```
### Install the chaosindy package in the python virtual environment:
```
(chaostk) ubuntu@client1:~$ python3 setup.py develop
```
Dependencies are being installed in a python virtualenv in your
~/.venvs directory. Nothing is installed in system-wide site-packages.
Therefore, do not run the above command with sudo.

## Configuration
### SSH
Python Fabric needs to know how to connect to each node without a password:
#### ~/.ssh/config
“Evernym-QA-New” in the IdentifyFile path below is a collection of PEM files
provided by the QA team used when setting up a test cluster.

Add an entry in ~/.ssh/config for every entry in a cluster’s
pool_trasactions_genesis file. The Host and Hostname are taken from
txnMetadata.txn.data.data.alias and txnMetadata.txn.data.data.node_ip
respectively. A helper script will likely be created that will generate a
~/.ssh/config file from a pool_transactions_genesis file.

Host Node1
    User ubuntu
    Hostname 1.2.3.4
    IdentityFile /home/ubuntu/pemfiles/node1.pem

"Node1" is used as the node's alias from the genesis transaction file
"ubuntu" is the login name to use when logging into Node1
"1.2.3.4" is the IP address to use when logging into Node1
"/home/ubuntu/pemfiles/node1.pem" is the pem file containing the private key to
use to login to Node1 as user ubuntu. The ubuntu user must have the public key
in it's /home/ubuntu/.ssh/authorized_keys file.

#### Test SSH connectivity
Test your SSH configuration for each client and validator node in your cluster/pool:
```
$ ssh Node1

Last login: Tue Jul 17 19:40:31 2018 from 5.6.7.8
ubuntu@node1:~$
```

You should be able to login as the designated user (user ‘ubuntu’ in this case)
to each node without a password.

### sudo
Some experiments may require probes and/or actions to run with sudo level
permissions. Test that the user configured in ~/.ssh/config for each host has
passwordless sudo rights.
```
ubuntu@kellysaopaulo1:~$ sudo su -
root@kellysaopaulo1:~#
```
The ‘ubuntu’ user in the above example either needs to be a member of the sudo
group or have a `ubuntu ALL=NOPASSWD: ALL` entry in /etc/sudoers
```
ubuntu@kellysaopaulo1:~$ groups
ubuntu adm dialout cdrom floppy sudo audio dip video plugdev netdev lxd
```
Note that the ubuntu user is a member of group *sudo*

### Recording
Indy Node’s recording feature provides a deterministic way of reproducing,
visually debugging, and fixing faults and failures. Add the following property
to /etc/indy/indy_config.py and restart the indy-node service.
```
STACK_COMPANION = 1
```

# Executing Experiments
Each chaosindy experiment has a an associated “run” script.

Experiments can be executed from any host where the following is true:
chaosindy is installed and configured (~/.ssh/config, etc…)
All client and validator nodes referenced in “run” scripts are reachable.

A python script capable of running any experiment may eventually be written,
but until then, each experiment will have a “run” script that does the
following:

* Define default arguments
* Accept arguments to override defaults
* Execute the experiment one or more times
* Detect if the experiment succeeded or failed and terminate immediately
  following first failure.

### Sample _help_ output from the run-force-view-change run script
```(chaostk) ubuntu@KellyStableClientVirgina:~/chaosindy$ ./scripts/run-force-view-change -h
Usage: ./scripts/run-force-view-change
 required arguments: None
 optional arguments:
   -c|--cleanup
       Remove temporary files/directories created by the experiment?
       Default: Yes
       Valid Inputs (case insensitive): yes, y, 1, no, n, 0
   -e|--execution-count
       How many times to run the experiment.
       Default: 1
       Valid Input: Any positive number >= 1
   -g|--genesis-file
       Path to the target pool genesis transaction file.
       Default: /home/ubuntu/chaosindy/pool_transactions_genesis
   -h|--help
       Print script help/usage
   -n|--validator-nodes
       A JSON list of node names to include in the experiment. Usually
         the complete list from the genesis file. TODO: derive default
         from genesis file.
       Default: '["Node1", "Node2", "Node3", "Node4", "Node5", "Node6", "Node7", "Node8", "Node9", "Node10"]'
   -t|--write-nym-timeout
       How long to wait (seconds) before timing out while writing a NYM
         transaction.
       Default: 60
       Valid Input: Any positive number >= 1
   -s|--seed
       Seed to use to create DID/Verkey pair used to get validator info
         via indy-cli. Must be a Trustee or Steward seed.
       Default: 000000000000000000000000Trustee1
       Valid Input: A 32 byte string. See default above for an example.
```
### Sample execution - Run the force-view-change experiment 1000 times
```
(chaostk) ubuntu@KellyStableClientVirgina:~/chaosindy$ ./scripts/run-force-view-change -e 1000
```
The run-force-view-change experiment will exit with a non-zero exit code as
soon as the first failed force-view-change experiment is encountered. Otherwise,
it will run 1000 iterations of the experiment and exist with a zero exit code.
