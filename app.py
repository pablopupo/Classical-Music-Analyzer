from flask import Flask

app = Flask(__name__)

@app.route('/')
def home():
    return "Hello, Classical Music Analysis Tool!"

if __name__ == '__main__':
    app.run(debug=True)
