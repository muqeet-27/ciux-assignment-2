from flask import Flask, render_template, request, jsonify
import pandas as pd
from nlu import parse
from service import execute

app = Flask(__name__)
df = pd.read_excel("data/people.xlsx")
df["DOB"] = pd.to_datetime(df["DOB"])


@app.route("/")
def index():
    return render_template("index.html")


@app.post("/chat")
def chat():
    msg = request.json.get("message", "")
    parsed = parse(msg, df)
    answer = execute(parsed, df)
    return jsonify(answer=answer, debug=parsed)


if __name__ == "__main__":
    app.run(debug=True)
