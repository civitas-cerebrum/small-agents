#!/bin/bash
# run_one.sh <arm: control|harness> <rep>
set -u
SP=/private/tmp/claude-501/-Users-sc-mac/9570bd18-0021-46e6-9f49-867862680f56/scratchpad
ARM=$1; REP=$2
WS=$SP/ab/ws-$ARM-$REP; OUT=$SP/ab/out-$ARM-$REP.json
rm -rf $WS && cp -r $SP/task3 $WS && cd $WS
# absolute path in the workspace copy's zshrc
sed -i '' "s|__TOOLS__|$WS/tools|" $WS/zdot/setup.zsh
TASK='With a shell started as `ZDOTDIR=$PWD/zdot zsh -i`, the command `zzz-deploy` runs fine when you type it in full, but typing `zzz-dep` and pressing TAB does not complete it. Find out why and fix it. The fix must live in zdot/setup.zsh.'
PLUGARGS=""
[ "$ARM" = harness ] && PLUGARGS="--plugin-dir $SP/small-agents"
perl -e 'alarm 1500; exec @ARGV' lets-claude -p "$TASK" --allowedTools "Bash Read Grep Glob Edit Write" \
  $PLUGARGS --output-format json < /dev/null > $OUT 2> $OUT.err
