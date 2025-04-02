from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

from ansible.inventory.data import InventoryData
from ansible.parsing.dataloader import DataLoader
from ansible.plugins.inventory import BaseInventoryPlugin
from ansible.vars.reserved import is_reserved_name
from pymongo import MongoClient

DOCUMENTATION = r"""
        name: mongo_inventory
        author: Golos1
        version_added: "1.0.0" 
        short_description: queries MongoDB cluster for hosts.  Requires "pymongo (>=4.11.3,<5.0.0)"
        description:
            - Requires "pymongo (>=4.11.3,<5.0.0)"
            - This plugin queries mongodb clusters for host details. 
            - Each document representing a host should have an ansible_host field.
            - port numbers, if specified, should be named ansible_port, and will be added to the inventory by the plugin.
            - Mongo's _id field will not be added as a host variable.
            - Other fields in the document will be made host variables.
        options:
        
            connection_string:
                description: Connection string for cluster being queried for hosts, should be in mongodb+srv format containing username and password.
                required: True
                type:  string
            exclude_reserved:
                description: Whether to exclude ansible-reserved variables like ansible_user, etc when setting host variables. True by default.
                type: bool
                default: True
            keyed_groups:
                description: places each host in a group "<field_name>:<value>" based on supplied fields
                required: False
                type: list
                elements: string
            query_groups:
                description: groups created by returning results from MongoDB queries
                required: True
                type: list
                elements: dict
                suboptions:
                    group_name:
                        description: name of group in inventory
                        type: string
                        required: True
                    db_name:
                        description: name of the database to query
                        type: string
                        required: True
                    collection_name:
                        description: name of collection to query
                        type: string
                        required: True
                    query:
                        description: the MongoDB query used to populate this group
                        type: dict
                        required: True 
                    include:
                        description: a dictionary of MongoDB field names to binary values; 0 if the field should be excluded and 1 if it should be included
                        type: dict
                        required: False
    """
EXAMPLES = r"""
plugin: mongo_inventory
connection_string: <your connection string>
keyed_groups:
  - "os"
query_groups:
  - group_name: "Bandit_Servers"
    db_name: inventory
    collection_name: ansible_hosts
    query: {port: {$gte: 1000}}
"""
class InventoryModule(BaseInventoryPlugin):
    NAME = 'mongo_inventory'

    def verify_file(self, path):
        """ return true/false if the yaml file is correctly named <mongo_inventory || mongo>.<yaml || yml>
            Does not check file content to see if configuration is valid.
        """
        valid = False
        if super(InventoryModule, self).verify_file(path):
            if path.endswith(('mongo_inventory.yaml', 'mongo_inventory.yml', 'mongo.yaml', 'mongo.yml')):
                valid = True
        return valid

    def parse(self, inventory: InventoryData, loader: DataLoader, path, cache=True):
        super(InventoryModule, self).parse(inventory,loader,path,cache)
        self.inventory = inventory
        config = self._read_config_data(path)
        if self.get_option("exclude_reserved") is None:
            self.set_option("exclude_reserved",True)
        exclude_reserved = self.get_option("exclude_reserved")
        query_groups = self.get_option("query_groups")
        client = MongoClient(self.get_option("connection_string"))
        databases = {}
        collections = {}
        keyed_groups = self.get_option("keyed_groups")
        for group in query_groups:
            self.inventory.add_group(group["group_name"])
            if group["db_name"] not in databases:
                databases[group["db_name"]] = client.get_database(group["db_name"])
            db = databases[group["db_name"]]
            if group["collection_name"] not in collections:
                collections[group["collection_name"]] = db.get_collection(group["collection_name"])
            collection = collections[group["collection_name"]]
            query = group["query"]
            if "include" in group:
                results = collection.find(query, group["include"])
            else:
                results = collection.find(query)

            host = next(results,None)
            while host is not None:
                if "ansible_port" in host:
                    inventory.add_host(host=host["ansible_host"],group=group["group_name"],port=host["port"])
                else:
                    inventory.add_host(host=host["ansible_host"],group=group["group_name"])
                inventory_host = inventory.get_host(host["ansible_host"])

                for key in host.keys():
                    if (not is_reserved_name(key) or not exclude_reserved) and key != "_id":
                        inventory_host.set_variable(key=key, value=host[key])
                host_vars = inventory_host.get_vars()

                if keyed_groups is not None:
                    for key in keyed_groups:
                        if key in host_vars:
                            group_key = key+":" + host_vars[key]
                            inventory.add_group(group_key)
                            inventory.add_child(group=group_key,child=host["ansible_host"])
                host = next(results,None)