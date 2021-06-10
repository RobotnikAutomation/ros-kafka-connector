#!/usr/bin/env python3

import rospy
from rospy_message_converter import message_converter
from rospy_message_converter import json_message_converter

import rosbridge_library.internal.ros_loader as ros_loader

import uuid

from confluent_kafka import Producer, Consumer, KafkaError, KafkaException


class ros_publish():

    def __init__(self):

        # initialize node
        rospy.init_node("ros_publish")
        rospy.on_shutdown(self.shutdown)

        # Retrieve parameters from launch file
        bootstrap_server = rospy.get_param("~bootstrap_server", "localhost:9092")

        self.group_id = rospy.get_param("~group_id", None)
        if self.group_id == "no-group":
            self.group_id = None

        self.ssl_cafile = rospy.get_param("~ssl_cafile", '../include/certificate.pem')
        self.ssl_keyfile = rospy.get_param("~ssl_keyfile", "../include/kafka.client.keystore.jks")
        self.ssl_password = rospy.get_param("~ssl_password", "password")
        self.ssl_security_protocol = rospy.get_param("~ssl_security_protocol", "SASL_SSL")
        self.ssl_sasl_mechanism = rospy.get_param("~ssl_sasl_mechanism", "PLAIN")
        self.sasl_username = rospy.get_param("~sasl_plain_username", "username")
        self.sasl_password = rospy.get_param("~sasl_plain_password", "password")

        self.ros_topic = rospy.get_param("~ros_topic", "test")
        self.kafka_topic = rospy.get_param("~kafka_topic", "bar")
        self.msg_type = rospy.get_param("~msg_type", "std_msgs/String")

        self.show_received_msg = rospy.get_param("~show_received_msg", False)
        self.show_received_json = rospy.get_param("~show_received_json", False)

        # Create kafka consumer
        # TODO: check possibility of using serializer directly (param value_deserializer from KafkaConsumer)
        self.consumer = Consumer({
            'bootstrap.servers': bootstrap_server,
            'sasl.mechanism': self.ssl_sasl_mechanism,
            'security.protocol': self.ssl_security_protocol,
            'sasl.username': self.sasl_username,
            'sasl.password': self.sasl_password,
            'group.id': str(uuid.uuid1()),  # this will create a new consumer group on each invocation.
            'auto.offset.reset': 'earliest',
            'error_cb': self.error_cb,
        })
        self.consumer.subscribe([self.kafka_topic])

        self.received_messages_in_total = 0
        self.debug_info_period = rospy.get_param("~debug_info_period", 10)
        if self.debug_info_period != 0:
            self.received_messages_until_last_debug_period = 0
            self.debug_info_timer = rospy.Timer(rospy.Duration(self.debug_info_period), self.debug_callack)

        # Import msg type
        msg_func = ros_loader.get_message_class(self.msg_type)

        # Subscribe to ROS topic of interest
        self.publisher = rospy.Publisher(self.ros_topic, msg_func, queue_size=10)
        rospy.loginfo("Using {} MSGs: {} -> ROS: {}".format(self.msg_type, self.kafka_topic, self.ros_topic))

    def debug_callack(self, event):
        received_messages = self.received_messages_in_total - self.received_messages_until_last_debug_period
        self.received_messages_until_last_debug_period = self.received_messages_in_total
        rospy.loginfo('From Kafka: %s to ROS %s: Received %d in %1.1f seconds (total %d)', self.kafka_topic, self.ros_topic, received_messages, self.debug_info_period, self.received_messages_in_total)

    # def kafka_or_avro_log(self):
    #     return ("AVRO", "KAFKA")[self.use_avro]

    def run(self):
        while not rospy.is_shutdown():
            msg = self.consumer.poll(0.1) # Wait for message or event/error
            if msg is None:
                # No message available within timeout.
                # Initial message consumption may take up to `session.timeout.ms` for
                #   the group to rebalance and start consuming.
                continue
            if msg.error():
                # Errors are typically temporary, print error and continue.
                print('Consumer error: {}'.format(msg.error()))
                continue
            ros_msg = None
            self.received_messages_in_total += 1
            try:
                # msg is of type bytes and needs a conversion to string
                ros_msg = json_message_converter.convert_json_to_ros_message(self.msg_type, msg.value().decode("utf-8"))
                if self.show_received_json:
                    rospy.loginfo(msg.value().decode("utf-8"))
            except ValueError as e:
                rospy.logwarn(str(e) + ': probably you are receiving an avro-encoded message, but trying to process it as a plain message')
            except Exception as e:
                rospy.logwarn(str(e) + ': time to debug!')

            if ros_msg != None:
                self.publisher.publish(ros_msg)


    def error_cb(err):
        """ The error callback is used for generic client errors. These
            errors are generally to be considered informational as the client will
            automatically try to recover from all errors, and no extra action
            is typically required by the application.
            For this example however, we terminate the application if the client
            is unable to connect to any broker (_ALL_BROKERS_DOWN) and on
            authentication errors (_AUTHENTICATION). """

        print("Client error: {}".format(err))
        if err.code() == KafkaError._ALL_BROKERS_DOWN or \
        err.code() == KafkaError._AUTHENTICATION:
            # Any exception raised from this callback will be re-raised from the
            # triggering flush() or poll() call.
            raise KafkaException(err)

    def shutdown(self):
        self.consumer.close()
        rospy.loginfo("Shutting down")

if __name__ == "__main__":

    try:
        node = ros_publish()
        node.run()
    except rospy.ROSInterruptException:
        pass

    rospy.loginfo("Exiting")
