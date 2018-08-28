"""
Chaos 'actions' module.

This module contains *actions* that modify the state of an indy-node pool.

By design, chaostoolkit runs an experiment if and only if 'steady state' is met.
Steady state is composed of one or more 'probes'. Probes gather and return
system state data. An experiment defines a 'tolerance' (predicate) for each
probe that must be true before the next probe is executed. All probes must pass
the tolerance test before the system is considered to be in a steady state.

When the steady state is met, the 'method' of the experiment will execute. An
experiment's 'method' is composed of a list of one or more '*actions*' that
introduce 'chaos' (change state, impede traffic, induce faults, etc.) into the
distributed system.

*Actions* are executed in the order they are declared. Faults, failures, and
exceptions encountered while executing an *action* do NOT cause an experiment to
fail.

All chaostoolkit cares about is if the steady state hypothesis is met before and
after the method executes. However, a chaos engineer may consider a 'succeeded'
result a failure if one or more of the *actions* encountered an exception,
failure, etc.

Each action's results are logged in the experiment's 'journal'. Manually or
programmatically inspecting an experiment's journal may be required to decide if
an experiment truely 'succeeded' or 'failed'.

*Actions* applied to a system (changes, faults, etc.) should not cause
predicatable failure. The purpose of an experiment is to introduce chaos to
expose weakness/vulnerability, bottlenecks/inefficiency, etc. without causing
systemic failure. If systemic failure is the result, either a bug exists or the
experiment is too aggressive.

Things to consider when adding or modifying *actions*:
1. *Actions* and Probes could/may be used outside of Chaos experiments for other
   kinds of integration or systems testing. Therefore, *actions* should
   be written in a way they can reused outside of the context of the
   chaostoolkit.
"""
