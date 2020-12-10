#!/usr/bin/python

import sys

import rospy
import rosbridge_library.internal.ros_loader as ros_loader

import json

import avro.schema

#raw_schema = open(sys.argv[1])
#json_schema = json.load(raw_schema)

PRINT_INFO = True

def convert_avro_name_to_ros_name(name):
    if name == 'boolean':
        return 'bool'
    if name == 'int':
        return 'int32'
    if name == 'long':
        return 'int64'
    if name == 'float':
        return 'float32'
    if name == 'double':
        return 'float64'
    if name == 'bytes':
        return 'byte[]'
    if name == 'string':
        return 'string'
    return ''

def process_union_schema(schema):
    union_type = []
    for sc in schema.schemas:
        if hasattr(sc, 'fullname'):
            if sc.fullname != 'null':
                union_type.append(sc.fullname)
        elif hasattr(sc, 'name'):
            if sc.name != 'null':
                union_type.append(sc.name)
                print 'has name'
        elif type(sc) == avro.schema.ArraySchema:
            return sc.items.name
    if len(union_type) >= 2 or len(union_type) == 0:
        raise
    return convert_avro_name_to_ros_name(union_type[0])

def process_enum_schema(schema):
    symbols = ''
    for s in schema.symbols:
        symbols += 'string ' + s + '=' + s + '\n'
    return symbols

def process_record_schema(schema, outfile=None):
    schemas_to_parse = []
    for field_key in schema.fields_dict:
        field = schema.fields_dict[field_key]
        if type(field.type) == avro.schema.PrimitiveSchema:
            line = convert_avro_name_to_ros_name(field.type.fullname) + ' ' + field.name
            if PRINT_INFO: print line
            outfile.write(line + '\n')
        elif type(field.type) == avro.schema.ArraySchema:
            line = field.type.items.name + '[] ' + field.name
            if PRINT_INFO: print line
            outfile.write(line + '\n')
            schemas_to_parse.append(field.type.items)
        elif type(field.type) == avro.schema.UnionSchema:
            line = process_union_schema(field.type) + ' ' + field.name
            if PRINT_INFO: print line
            outfile.write(line + '\n')
        elif type(field.type) == avro.schema.EnumSchema:
            line = process_enum_schema(field.type)
            line += 'string ' + field.name + '\n'
            if PRINT_INFO: print line
            outfile.write(line + '\n')
        else:
            object_name = field.type.name if field.type.name != 'DataObject' else schema.name + 'DataObject'
            line = object_name + ' ' + field.name
            if PRINT_INFO: print line
            outfile.write(line + '\n')
            schemas_to_parse.append(field.type)
    return schemas_to_parse

print 'PROCESSING FILE: ' + sys.argv[1]
try:
    schemas = [avro.schema.parse(open(sys.argv[1]).read())]
except:
    print 'ERROR'
    sys.exit(-1)

basename = sys.argv[1][0:-5]

while len(schemas) != 0:
    new_schemas = []
    for schema in schemas:
        msg_filename = schema.name if schema.name != 'DataObject' else basename + 'DataObject'
        msg_file = open(msg_filename + '.msg', 'wt')
        ns = process_record_schema(schema, msg_file)
        print ''
        new_schemas.extend(ns)
        msg_file.close()
    schemas = new_schemas

