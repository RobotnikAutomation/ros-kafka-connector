# ROS Package: ros_kafka_connector 

This is a ROS package for subscribing or publishing to topics using Kafka, with typed messages using AVRO schemas

| Parameter       |  Info           | Default  |
| ------------- |:-------------:| -----:|
| bootstrap_server | IP of kafka server | "localhost:9092" |
| kafka_topic | topic name found in Kafka |  "test" |
| ros_topic | topic name found in ROS |    "test" |
| msg_type | full ROS message name |    "std_msgs/String" |
| avro_subject | full AVRO subject name |    "string-value" |

ROS message types are supported as long as they exist.

## Requirements

```https://github.com/verisign/python-confluent-schemaregistry```

## Publish to ROS topic
```
$ roslaunch ros_kafka_connector ros_publish.launch
```
After updating the launch file with the correct settings for your topic, you can test it by pubishing a json to your kafka topic using a kafka publisher. The String message json is simple: {'data': 'Hello world!'}

You could also send the message to the kafka server through python with the following script.

#### Install kafka library
```
$ pip install kafka-python
```
#### python script (without avro schema)
```
from kafka import KafkaProducer
kafka_topic = 'test'
msg = 'Hello World!'
producer = KafkaProducer(bootstrap_servers="localhost:9092", value_serializer=lambda x: json.dumps(x).encode('ascii')) 
producer.send(kafka_topic, {'data': msg})          # 'data' is part of the string message definition
```

## Publish to Kafka topic
```
$ roslaunch ros_kafka_connector kafka_publish.launch
```

To test this node you can simply type...

#### Terminal

```
$ roscore
$ rostopic pub -r 3 /test std_msgs/String "data: 'Hello World!'"
```

This will output the hello world at 3 hz to the "/test" ROS topic. To confirm this works you can open up another terminal and type in 
"rostopic echo /test" which should show you the same message is being published to ROS. This message should also be published to the Kafka topic.

