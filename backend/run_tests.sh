#!/usr/bin/env bash
cd /c/Users/cjbig/Desktop/EDON/edon-cav-engine/edon_gateway
python -m pytest edon_gateway/test/ -v --tb=short 2>&1 | tee /c/Users/cjbig/Desktop/EDON/edon-cav-engine/edon_gateway/test_output.txt
