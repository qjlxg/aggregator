name: Run esc.py

on:
  workflow_dispatch:

jobs:
  run-script:
    runs-on: ubuntu-latest

    steps:
    - uses: actions/checkout@v4

    - name: Set up Python
      uses: actions/setup-python@v5
      with:
        python-version: '3.11'

    - name: Install dependencies
      run: |
        python -m pip install --upgrade pip
        pip install -r requirements.txt

    - name: Run esc.py
      run: python esc.py

    - name: Upload result files
      uses: actions/upload-artifact@v4
      with:
        name: result-files
        path: |
          data/A.txt
          data/c.yml
          data.b.cvs
