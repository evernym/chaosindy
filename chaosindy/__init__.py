"""
chaosindy module

This module contains:
 - actions that modify the state of an indy-node pool. (actions directory)
 - probes that gather data/information about indy-node pool state. (probes
   directory)
 - helper functions (helper.py file)
 - common files (common directory)
 - A remote execution tool built on Python Fabric (execute directory).

At minimum, this module is intended to provide all primitive operations needed
to compose chaos experiments for Indy Node. The idea is to give the experiment
writer as much flexibility as possible.

It is encouraged that useful/reusable combinations of primitive operations be
maintained in this module. If multiple experiments combine primitives to achieve
the same outcome, the principle of code reuse suggests a the combination be
captured and exposed as a new operation and the experiments would be refactored
to use the new operation.

By design, chaostoolkit runs an experiment if and only if 'steady state' is met.
Steady state is composed of one or more 'probes'. Probes gather and return
system state data. An experiment defines a 'tolerance' (predicate) for each
probe that must be true before the next probe is executed. All probes must pass
the tolerance test before the system is considered to be in a steady state.

When the steady state is met, the 'method' of the experiment will execute. An
experiment's 'method' is composed of a list of one or more 'actions' that
introduce 'chaos' (change state, impede traffic, induce faults, etc.) into the
distributed system.

Actions are executed in the order they are declared. Faults, failures, and
exceptions encountered while executing an action do NOT cause an experiment to
fail.

All chaostoolkit cares about is if the steady state hypothesis is met before and
after the method executes. However, a chaos engineer may consider a 'succeeded'
result a failure if one or more of the actions encountered an exception,
failure, etc.

Each action's results are logged in the experiment's 'journal'. Manually or
programmatically inspecting an experiment's journal may be required to decide if
an experiment truely 'succeeded' or 'failed'.

Actions applied to a system (changes, faults, etc.) should not cause
predicatable failure. The purpose of an experiment is to introduce chaos to
expose weakness/vulnerability, bottlenecks/inefficiency, etc. without causing
systemic failure. If systemic failure is the result, either a bug exists or the
experiment is too aggressive.

Things to consider when adding or modifying actions and/or probes:
1. Actions and Probes could/may be used outside of Chaos experiments for other
   kinds of integration or systems testing. Therefore, actions should
   be written in a way they can reused outside of the context of the
   the chaosindy module and the chaostoolkit.
"""
