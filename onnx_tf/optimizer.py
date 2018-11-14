from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
from __future__ import unicode_literals

import tensorflow as tf
import argparse

import onnx
from onnx import defs
from onnx import mapping
from onnx.helper import make_model
from onnx.helper import make_opsetid

from onnx_tf.backend import run_node
from onnx_tf.common import exception
from onnx_tf.common.handler_helper import get_all_frontend_handlers
from onnx_tf.common import IS_PYTHON3
from onnx_tf.handlers.frontend_handler import FrontendHandler
from onnx_tf.pb_wrapper import TensorflowNode
from onnx_tf.pb_wrapper import OnnxGraph

def parse_args(args):
  parser = argparse.ArgumentParser(
      description=
      "onnx-tensorflow optimization passes."
  )
  parser.add_argument(
      "--infile",
      "-i",
      help="Path to the ONNX model being optimized.",
      required=True)
  parser.add_argument(
      "--outfile", "-o", help="Output file path for the optimized ONNX model.", required=True)
  return parser.parse_args(args)

def constant_folding(onnx_graph):
  for node in onnx_graph.nodes_proto:
    # See if all inputs are present as contant tensors.
    inclusion_mask = map(lambda x: x in onnx_graph.consts, node.input)
    all_constant = all(inclusion_mask)
    # If all inputs are constant, then fold this constant node.
    if all_constant:
      print("Folding ", node.name, node.op_type)
      const_inputs = list(map(lambda x: onnx_graph.consts[x], node.input))
      outputs = run_node(node, const_inputs)
      # Make output tensors appear as graph initializers.
      for index, output_name in enumerate(node.output):
        output_content = outputs[index]
        output_onnx_type = mapping.NP_TYPE_TO_TENSOR_TYPE[output_content.dtype]
        onnx_graph.add_const_explicit(name=output_name, value=output_content)
        onnx_graph.add_const_proto_explicit(
            name=output_name,
            value=output_content,
            onnx_dtype=output_onnx_type)
        onnx_graph.add_input_proto_explicit(
            name=output_name,
            shape=output_content.shape,
            onnx_dtype=output_onnx_type)
      # Remove this folded constant node from graph.
      onnx_graph.remove_node_proto(node.name)
  return onnx_graph

all_optimization_passes = {
  "CONSTANT_FOLDING": constant_folding
}

all_optimization_pass_names = all_optimization_passes.keys()

def optimize(onnx_graph, passes=all_optimization_pass_names):
  """Optimize ONNX graph.
  """
  for opt_pass in passes:
    assert opt_pass in all_optimization_passes.keys()
    opt_func = all_optimization_passes[opt_pass]
    onnx_graph = opt_func(onnx_graph)
    return onnx_graph

def main(args):
  args = parse_args(args)
  passes = ["CONSTANT_FOLDING"]
  onnx_model = onnx.load(args.infile)
  onnx_graph = OnnxGraph(graph_proto=onnx_model.graph)
  onnx_graph = optimize(onnx_graph, passes)
  onnx_model.graph.CopyFrom(onnx_graph.make_graph_proto())
  onnx.save(onnx_model, args.outfile)
