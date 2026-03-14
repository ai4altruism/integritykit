#!/bin/bash
# demo/run_all.sh


echo ">>> Injecting scenario signals..."
docker exec integritykit-app python demo/simulate_scenario.py

echo ""
echo ">>> Running facilitator workflow..."
sleep 2
docker exec integritykit-app python demo/run_facilitator_demo.py

echo ">>> Demo Complete!"
