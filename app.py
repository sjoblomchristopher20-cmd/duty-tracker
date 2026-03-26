from flask import Flask, request, jsonify

app = Flask(__name__)

users = []

@app.route('/')
def home():
	return "Duty Tracker Running"

@app.route('/add_user', methods=['POST'])
def add_user():
	data = requesst.json
	usesr.append(data)
	return jsonify({"message": "User added", "usesrs": users})

@app.route('/users', methods=['GET'])
def get_users():
	return jsonify(users)

if __name__== '__main__':
	app.run(host='0.0.0.0', port=8080)
