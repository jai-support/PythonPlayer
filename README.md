# Flask web player
This application is developed on windows 11 and haven't been tested on ubuntu
There is no certainty that this code will execute without problems. Since computers have different specs.

## Windows
Since this project uses some of the packages from the python eBUS SDK, we'll just install it into a Venv to easily link to these files.
If its the first time running scripts in powershell you might need to change your ExecutionPolicy (needs admin privileges)

```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned
```


### Setup Env
First we create an env, then we activate it
```powershell
python -m venv env
env\Scripts\activate.ps1
```
### Install eBUS
Download the correct version of eBUS python from our website: https://www.jai.com/support-software/jai-software

Then install it in the terminal that you activated the venv
```powershell 
pip install .\ebus_python-<EBUS VERSION>.whl opencv_python
pip install -r requirements.txt
```

### Run the Code
Lastly run the code, both webapp.py and camera.py can be execute with different results. 
camera.py is a simple acquisition app using OpenCV to display
webapp.py is a Flask based acquisition app with some amount of control to play around with

```powershell
python web.py
```