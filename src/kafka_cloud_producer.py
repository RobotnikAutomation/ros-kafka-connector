#!/usr/bin/env python3

import rospy
from rospy_message_converter import message_converter
from rospy_message_converter import json_message_converter
import rosbridge_library.internal.ros_loader as ros_loader

from confluent_kafka import Producer

class kafka_publish():

    def __init__(self):

        # initialize node
        rospy.init_node("kafka_publish")
        rospy.on_shutdown(self.shutdown)

        # Retrieve parameters from launch file
        bootstrap_server = rospy.get_param("~bootstrap_server", "localhost:9092")            

        self.ssl_cafile = rospy.get_param("~ssl_cafile", 'certificate.pem')
        self.ssl_keyfile = rospy.get_param("~ssl_keyfile", "kafka.client.keystore.jks")
        self.ssl_password = rospy.get_param("~ssl_password", "password")
        self.ssl_security_protocol = rospy.get_param("~ssl_security_protocol", "SASL_SSL")
        self.ssl_sasl_mechanism = rospy.get_param("~ssl_sasl_mechanism", "PLAIN")
        self.sasl_plain_username = rospy.get_param("~sasl_plain_username", "username")
        self.sasl_plain_password = rospy.get_param("~sasl_plain_password", "password")

        self.ros_topic = rospy.get_param("~ros_topic", "test")
        self.msg_type = rospy.get_param("~msg_type", "std_msgs/String")
        self.kafka_topic = rospy.get_param("~kafka_topic", "bar")

        self.show_sent_msg = rospy.get_param("~show_sent_msg", False)
        self.show_sent_json = rospy.get_param("~show_sent_json", False)

        # Create kafka producer
        # TODO: check possibility of using serializer directly (param value_serializer from KafkaProducer)
        self.producer = Producer({'bootstrap.servers':bootstrap_server,
                                    'sasl.mechanism':self.ssl_sasl_mechanism,
                                    'security.protocol':self.ssl_security_protocol,
                                    'sasl.username':self.sasl_plain_username,
                                    'sasl.password':self.sasl_plain_password
        })

        # ROS does not allow a change in msg type once a topic is created. Therefore the msg
        # type must be imported and specified ahead of time.
        msg_func = ros_loader.get_message_class(self.msg_type)

        self.received_messages_in_total = 0
        self.debug_info_period = rospy.get_param("~debug_info_period", 10)
        if self.debug_info_period != 0:
            self.received_messages_until_last_debug_period = 0
            self.debug_info_timer = rospy.Timer(rospy.Duration(self.debug_info_period), self.debug_callack)

        # Subscribe to the topic with the chosen imported message type
        rospy.Subscriber(self.ros_topic, msg_func, self.callback)
        rospy.loginfo("Using {} MSGs from ROS: {} -> KAFKA: {}".format(self.msg_type, self.ros_topic, self.kafka_topic))

    def debug_callack(self, event):
        received_messages = self.received_messages_in_total - self.received_messages_until_last_debug_period
        self.received_messages_until_last_debug_period = self.received_messages_in_total
        rospy.loginfo('From ROS: %s to KAFKA %s: Received %d in %1.1f seconds (total %d)', self.ros_topic, self.kafka_topic, received_messages, self.debug_info_period, self.received_messages_in_total)

    def callback(self, msg):
        self.received_messages_in_total += 1

        # Output msg to ROS and send to Kafka server
        if self.show_sent_msg:
            rospy.loginfo("MSG Received: {}".format(msg))
        # Convert from ROS Msg to Dictionary
        msg_as_dict = message_converter.convert_ros_message_to_dictionary(msg)
        # also print as json for debugging purposes
        msg_as_json = json_message_converter.convert_ros_message_to_json(msg)
        if self.show_sent_json:
            rospy.loginfo(msg_as_json)
        # Convert from Dictionary to Kafka message
        # this way is slow, as it has to retrieve last schema
        # msg_as_serial = self.serializer.encode_record_for_topic(self.kafka_topic, msg_as_dict)
        try:
            self.producer.produce(self.kafka_topic, value=msg_as_json)
            # Trigger delivery report callbacks from previous produce calls.
            p.poll(0)

            # flush() is typically called when the producer is done sending messages to wait
            # for outstanding messages to be transmitted to the broker and delivery report
            # callbacks to get called. For continous producing you should call p.poll(0)
            # after each produce() call to trigger delivery report callbacks.
            p.flush(10)
        except Exception as e:
            rospy.logwarn(str(e) + ': time to debug!')

    def run(self):
        rate = rospy.Rate(10)
        while not rospy.is_shutdown():
            rate.sleep()

    def shutdown(self):
        rospy.loginfo("Shutting down")

if __name__ == "__main__":

    try:
        node = kafka_publish()
        node.run()
    except rospy.ROSInterruptException:
        pass

    rospy.loginfo("Exiting")
