#!/usr/bin/env python

import rospy
from rospy_message_converter import message_converter
from rospy_message_converter import json_message_converter

import rosbridge_library.internal.ros_loader as ros_loader

from kafka import KafkaProducer
from kafka import KafkaConsumer

from confluent.schemaregistry.client import CachedSchemaRegistryClient
from confluent.schemaregistry.serializers import MessageSerializer


class Topic:
    def __init__(self, kafka_topic, ros_topic, ros_msg_type, avro_subject=None, avro_file=""):
        self.kafka_topic = kafka_topic
        self.ros_topic = ros_topic
        self.ros_msg_type = ros_msg_type
        self.avro_subject = avro_subject
        self.avro_file = avro_file

    def debug_callack(self, event):
        received_messages = self.received_messages_in_total - self.received_messages_until_last_debug_period
        self.received_messages_until_last_debug_period = self.received_messages_in_total
        rospy.loginfo('From ROS: %s to %s %s: Received %d in %1.1f seconds (total %d)', self.ros_topic, self.kafka_or_avro_log(), self.kafka_topic, received_messages, self.debug_info_period, self.received_messages_in_total)

    def kafka_or_avro_log(self):
        return ("AVRO", "KAFKA")[self.avro_subject!=None]


class comm_bridge():

    def __init__(self):

        # initialize node
        rospy.init_node("comm_bridge")
        rospy.on_shutdown(self.shutdown)

        # Retrieve parameters from launch file
        # Global Kafka parameters

        local_server = rospy.get_param("~local_server", False)
        if local_server:
            bootstrap_server = "localhost:9092"
            schema_server = "http://localhost:8081/"
            rospy.logwarn("Using Kafka local server.")
        else:
            bootstrap_server = rospy.get_param("~bootstrap_server", "localhost:9092")
            schema_server = rospy.get_param("~schema_server", "http://localhost:8081/")
        
        self.use_ssl = rospy.get_param("~use_ssl", False)
        self.use_avro = rospy.get_param("~use_avro", False)

        self.show_sent_msg = rospy.get_param("~show_sent_msg", False)
        self.show_sent_json = rospy.get_param("~show_sent_json", False)

        self.group_id = rospy.get_param("~group_id", None)
        if (self.group_id == "no-group"):
            self.group_id = None

        if (self.use_ssl):
            self.ssl_cafile = rospy.get_param("~ssl_cafile", '../include/certificate.pem')
            self.ssl_keyfile = rospy.get_param("~ssl_keyfile", "../include/kafka.client.keystore.jks")
            self.ssl_password = rospy.get_param("~ssl_password", "password")
            self.ssl_security_protocol = rospy.get_param("~ssl_security_protocol", "SASL_SSL")
            self.ssl_sasl_mechanism = rospy.get_param("~ssl_sasl_mechanism", "PLAIN")
            self.sasl_plain_username = rospy.get_param("~sasl_plain_username", "username")
            self.sasl_plain_password = rospy.get_param("~sasl_plain_password", "password")

        # from Kafka to ROS topics parameters
        list_from_kafka_topics = rospy.get_param("~list_from_kafka", [])
        self.list_from_kafka = []
        for item in list_from_kafka_topics:
            # TODO: check if some value is missing
            self.list_from_kafka.append(Topic(item["kafka_topic"], "from_kafka/"+item["ros_topic"],
                                         item["ros_msg_type"]))
        
        # from ROS to Kafka topics parameters
        list_to_kafka_topics = rospy.get_param("~list_to_kafka", [])
        self.list_to_kafka = []
        for item in list_to_kafka_topics:
            # TODO: check if some value is missing
            self.list_to_kafka.append(Topic(item["kafka_topic"], "to_kafka/"+item["ros_topic"],
                                         item["ros_msg_type"], item["avro_subject"], item["avro_file"]))

        # Create schema registry connection and serializer
        self.client = CachedSchemaRegistryClient(url=schema_server)
        self.serializer = MessageSerializer(self.client)

        if (self.use_avro):
            for topic in self.list_to_kafka:
                rospy.loginfo("Loading schema for " + topic.avro_subject + " from registry server")
                _, topic.avro_schema, _ = self.client.get_latest_schema(topic.avro_subject)

                if topic.avro_file != "":
                    rospy.loginfo("Loading schema for " + topic.avro_subject + " from file " + topic.avro_file + " as it does not exist in the server")
                    topic.avro_schema = avro.schema.parse(open(topic.avro_file).read())

                if topic.avro_schema is None:
                    rospy.logerr("cannot get schema for " + topic.avro_subject)

        # Create kafka consumer
        # TODO: check possibility of using serializer directly (param value_deserializer from KafkaConsumer)
        for topic in self.list_from_kafka:
            if(self.use_ssl):
                topic.consumer = KafkaConsumer(topic.kafka_topic,
                                        bootstrap_servers=bootstrap_server,
                                        security_protocol=self.ssl_security_protocol,
                                        ssl_check_hostname=False,
                                        ssl_cafile=self.ssl_cafile,
                                        ssl_keyfile=self.ssl_keyfile,
                                        sasl_mechanism=self.ssl_sasl_mechanism,
                                        ssl_password=self.ssl_password,
                                        sasl_plain_username=self.sasl_plain_username,
                                        sasl_plain_password=self.sasl_plain_password
                                        )
            else:
                topic.consumer = KafkaConsumer(topic.kafka_topic,
                                            bootstrap_servers=bootstrap_server,
                                            auto_offset_reset='latest',
                                            consumer_timeout_ms=5000,
                                            group_id=self.group_id
                                            )

            # Import msg type
            msg_func = ros_loader.get_message_class(topic.ros_msg_type)

            topic.received_messages_in_total = 0
            topic.debug_info_period = rospy.get_param("~debug_info_period", 10)
            if topic.debug_info_period != 0:
                topic.received_messages_until_last_debug_period = 0
                topic.debug_info_timer = rospy.Timer(rospy.Duration(topic.debug_info_period), topic.debug_callack)

            # Subscribe to ROS topic of interest
            topic.publisher = rospy.Publisher(topic.ros_topic, msg_func, queue_size=10)
            rospy.logwarn("Using {} MSGs from KAFKA: {} -> ROS: {}".format(topic.ros_msg_type, topic.kafka_topic, topic.ros_topic))

        # Create kafka producer
        # TODO: check possibility of using serializer directly (param value_serializer from KafkaProducer)
        for topic in self.list_to_kafka:
            if(self.use_ssl):
                topic.producer = KafkaProducer(bootstrap_servers=bootstrap_server,
                                            security_protocol=self.ssl_security_protocol,
                                            ssl_check_hostname=False,
                                            ssl_cafile=self.ssl_cafile,
                                            ssl_keyfile=self.ssl_keyfile,
                                            sasl_mechanism=self.ssl_sasl_mechanism,
                                            ssl_password=self.ssl_password,
                                            sasl_plain_username=self.sasl_plain_username,
                                            sasl_plain_password=self.sasl_plain_password
                                            )
            else:
                topic.producer = KafkaProducer(bootstrap_servers=bootstrap_server)

            # ROS does not allow a change in msg type once a topic is created. Therefore the msg
            # type must be imported and specified ahead of time.
            msg_func = ros_loader.get_message_class(topic.ros_msg_type)

            topic.received_messages_in_total = 0
            topic.debug_info_period = rospy.get_param("~debug_info_period", 10)
            if topic.debug_info_period != 0:
                topic.received_messages_until_last_debug_period = 0
                topic.debug_info_timer = rospy.Timer(rospy.Duration(topic.debug_info_period), topic.debug_callack)

            # Subscribe to the topic with the chosen imported message type
            rospy.Subscriber(topic.ros_topic, msg_func, self.callback, topic)
            rospy.logwarn("Using {} MSGs from ROS: {} -> KAFKA: {}".format(topic.ros_msg_type, topic.ros_topic, topic.kafka_topic))

    def callback(self, msg, topic):
        topic.received_messages_in_total += 1

        # Output msg to ROS and send to Kafka server
        if self.show_sent_msg:
            rospy.logwarn("MSG received from {}: {}".format(topic.ros_topic, msg))
        # Convert from ROS Msg to Dictionary
        msg_as_dict = message_converter.convert_ros_message_to_dictionary(msg)
        # also print as json for debugging purposes
        msg_as_json = json_message_converter.convert_ros_message_to_json(msg)
        if self.show_sent_json:
            rospy.logwarn(msg_as_json)
        # Convert from Dictionary to Kafka message
        # this way is slow, as it has to retrieve last schema
        # msg_as_serial = self.serializer.encode_record_for_topic(self.kafka_topic, msg_as_dict)
        if (self.use_avro):
            try:
                msg_as_serial = self.serializer.encode_record_with_schema(topic.kafka_topic, topic.avro_schema, msg_as_dict)
                topic.producer.send(topic.kafka_topic, value=msg_as_serial)
            except Exception as e:
                if topic.kafka_topic is None:
                    rospy.logwarn("kafka_topic is None")
                elif topic.avro_schema is None:
                    rospy.logwarn("Tryed connect with the topic: " + topic.kafka_topic + ", but the avro_schema is None. Was the schema registry?")
                else:
                    rospy.logwarn("Cannot publish to " + topic.kafka_topic + " with schema " + topic.avro_schema.name + ". Probably bad schema name on registry")
        else:
            try:
                topic.producer.send(topic.kafka_topic, value=msg_as_json)
            except Exception as e:
                if topic.kafka_topic is None:
                    rospy.logwarn("kafka_topic is None")
                else:
                    rospy.logwarn("Cannot publish to " + topic.kafka_topic + ". Probably bad topic name on registry")

    def run(self):
        while not rospy.is_shutdown():
            for topic in self.list_from_kafka:
                for msg in topic.consumer:
                    ros_msg = None
                    topic.received_messages_in_total += 1
                    rospy.logwarn("Received MSG from: " + topic.kafka_topic)
                    if (self.use_avro):
                        try:
                            # Convert Kafka message to Dictionary
                            msg_as_dict = self.serializer.decode_message(msg.value)
                            # Convert Dictionary to ROS Msg
                            ros_msg = message_converter.convert_dictionary_to_ros_message(topic.ros_msg_type, msg_as_dict, check_types=False)
                            if self.show_received_json:
                                rospy.loginfo(msg_as_dict)
                        except Exception as e:
                            rospy.logwarn(str(e) + ': time to debug!')
                    else:
                        try:
                            ros_msg = json_message_converter.convert_json_to_ros_message(topic.ros_msg_type, msg.value)
                            if self.show_received_json:
                                rospy.loginfo(msg.value)
                        except ValueError as e:
                            rospy.logwarn(str(e) + ': probably you are receiving an avro-encoded message, but trying to process it as a plain message')
                        except Exception as e:
                                rospy.logwarn(str(e) + ': time to debug!')
                    
                    # Publish to ROS topic
                    if ros_msg != None:
                        topic.publisher.publish(ros_msg)

    def shutdown(self):
        rospy.loginfo("Shutting down")

if __name__ == "__main__":

    try:
        node = comm_bridge()
        node.run()
    except rospy.ROSInterruptException:
        pass

    rospy.loginfo("Exiting")
