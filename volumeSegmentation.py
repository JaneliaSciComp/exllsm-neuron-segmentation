""" 
This script applies a pretrained model file to a sub-volume
of a large n5 volume.
"""
import argparse
import numpy as np
import time
import tensorflow as tf
from tqdm import tqdm
from tensorflow.keras.models import load_model

from tools.tilingStrategy import (AbsoluteCanvas, UnetTiling3D, UnetTiler3D)
from unet.model import (InputBlock, DownsampleBlock, BottleneckBlock,
                        UpsampleBlock, OutputBlock)
from tools.preProcessing import calculateScalingFactor, scaleImage
from tools.postProcessing import clean_floodFill, removeSmallObjects
from n5_utils import read_n5_block, write_n5_block


def _gpu_fix():
    # Fix for tensorflow-gpu issues
    gpus = tf.config.experimental.list_physical_devices('GPU')
    if gpus:
        # Currently, memory growth needs to be the same across GPUs
        for gpu in gpus:
            tf.config.experimental.set_memory_growth(gpu, True)

        logical_gpus = tf.config.experimental.list_logical_devices('GPU')
        print('Physical GPUs:', len(gpus), 'Logical GPUs:', len(logical_gpus))


def main():
    start_time = time.time()

    parser = argparse.ArgumentParser(description='Neuron segmentation')

    parser.add_argument('-i', '--input',
                        dest='input_path', type=str, required=True,
                        help='Path to the input n5')

    parser.add_argument('-id', '--input_data_set',
                        dest='input_data_set', type=str, default="/s0",
                        help='Path to input data set (default "/s0")')

    parser.add_argument('-od', '--output_data_set',
                        dest='output_data_set', type=str, default="/s0",
                        help='Path to output data set (default "/s0")')

    parser.add_argument('-m', '--model_path',
                        dest='model_path', type=str, required=True,
                        help='Path to the model')

    parser.add_argument('-s', '--scaling',
                        dest='scaling', type=float,
                        help='Tiles scaling factor')

    parser.add_argument('-o', '--output',
                        dest='output_path', type=str, required=True,
                        help='Path to the (already existing) output n5')

    parser.add_argument('--start',
                        dest='start_coord', type=str, required=True,
                        metavar='x1,y1,z1',
                        help='Starting coordinate (x,y,z) of block to process')

    parser.add_argument('--end',
                        dest='end_coord', type=str, required=True,
                        metavar='x2,y2,z2',
                        help='Ending coordinate (x,y,z) of block to process')

    parser.add_argument('--model_input_shape',
                        dest='model_input_shape', type=str,
                        metavar='dx,dy,dz', default='220,220,220',
                        help='Model input shape')

    parser.add_argument('--model_output_shape',
                        dest='model_output_shape', type=str,
                        metavar='dx,dy,dz', default='132,132,132',
                        help='Model output shape')

    parser.add_argument('--image_shape',
                        dest='image_shape', type=str, required=True,
                        metavar='dx,dy,dz',
                        help='Whole volume shape')

    parser.add_argument('--set_gpu_mem_growth', dest='set_gpu_mem_growth',
                        action='store_true', default=False,
                        help='If true set gpu memory growth')

    parser.add_argument('--with_post_processing', dest='with_post_processing',
                        action='store_true', default=False,
                        help='If true run the watershed segmentation')

    parser.add_argument('--as_binary_mask', dest='as_binary_mask',
                        action='store_true', default=False,
                        help='If true output the result as binary mask')

    parser.add_argument('--unet_batch_size', dest='unet_batch_size',
                        type=int, default=1,
                        help='High confidence threshold for region closing')

    parser.add_argument('-ht', '--high_threshold', dest='high_threshold',
                        type=float, default=0.98,
                        help='High confidence threshold for region closing')

    parser.add_argument('-lt', '--low_threshold', dest='low_threshold',
                        type=float, default=0.2,
                        help='Low confidence threshold for region closing')

    parser.add_argument('--small_region_probability_threshold',
                        dest='small_region_probability_threshold',
                        type=float, default=0.2,
                        help='Probability threshold for small region removal')

    parser.add_argument('--small_region_size_threshold',
                        dest='small_region_size_threshold',
                        type=int, default=2000,
                        help='Size threshold for small region removal')

    args = parser.parse_args()

    if args.set_gpu_mem_growth:
        _gpu_fix()

    start = tuple([int(d) for d in args.start_coord.split(',')])
    end = tuple([int(d) for d in args.end_coord.split(',')])

    model_input_shape = tuple([int(d) for d in args.model_input_shape.split(',')])
    model_output_shape = tuple([int(d) for d in args.model_output_shape.split(',')])

    # Parse the tiling subvolume from slice to aabb notation
    subvolume = np.array(start + end)
    subvolume_shape = tuple([end[i] - start[i] for i in range(len(end))])

    # Create a tiling of the subvolume using absolute coordinates
    print('targeted subvolume for segmentation:', subvolume)
    image_shape = tuple([int(d) for d in args.image_shape.split(',')])
    print('global image shape:', str(image_shape))
    tiling = UnetTiling3D(image_shape,
                          subvolume,
                          input_shape=model_input_shape,
                          output_shape=model_output_shape)

     # actual U-Net volume as x0,y0,z0,x1,y1,z1
    input_volume_aabb = np.array(tiling.getInputVolume())
    unet_start = [ np.max([0, d]) for d in input_volume_aabb[:3] ]
    unet_end = [ np.min([image_shape[i], input_volume_aabb[i+3]]) 
                    for i in range(3) ] # max extent is whole volume shape

    # Read part of the n5 based upon location
    unet_volume = np.array(unet_start + unet_end)

    print('Read U-Net volume', unet_start, unet_end, unet_volume)
    img = read_n5_block(args.input_path, args.input_data_set, unet_start, unet_end)

    # Calculate scaling factor from image data if no predefined value was given
    if args.scaling is None:
        # calculate scaling factor
        scalingFactor = calculateScalingFactor(img)
        print(f'Calculated a scaling factor {scalingFactor}')
    else:
        # Use scaling factor arg
        scalingFactor = args.scaling
        print(f'Using scaling factor {scalingFactor}')

    img = scaleImage(img, scalingFactor)

    # %% Load Model File
    # Restore the trained model. Specify where keras can
    # find custom objects that were used to build the unet
    unet = load_model(args.model_path, compile=False,
                      custom_objects={
                          'InputBlock': InputBlock,
                          'DownsampleBlock': DownsampleBlock,
                          'BottleneckBlock': BottleneckBlock,
                          'UpsampleBlock': UpsampleBlock,
                          'OutputBlock': OutputBlock
                      })

    print('The unet works with\ninput shape {}\noutput shape {}'.format(
        unet.input.shape, unet.output.shape))

    # Create an absolute Canvas from the input region
    # (this is the targeted output expanded by
    # adjacent areas that are relevant for segmentation)
    print('Create tiled input:', image_shape, unet_volume, img.shape)
    input_canvas = AbsoluteCanvas(image_shape,
                                  canvas_area=unet_volume,
                                  image=img)
    # Create an empty absolute canvas for
    # the targeted output region of the mask
    print('Create tiled output:', image_shape, subvolume, subvolume_shape)
    output_image = np.zeros(shape=subvolume_shape)
    output_canvas = AbsoluteCanvas(image_shape,
                                   canvas_area=subvolume,
                                   image=output_image)
    # Create the unet tiler instance
    tiler = UnetTiler3D(tiling, input_canvas, output_canvas)

    # Perform segmentation
    seg_start_time = time.time()

    def preprocess_dataset(x):
        # The unet expects the input data to have an additional channel axis.
        x = tf.expand_dims(x, axis=-1)
        return x

    predictionset_raw = tf.data.Dataset.from_generator(tiler.getGeneratorFactory(),
                                                       output_types=(
                                                           tf.float32),
                                                       output_shapes=(tf.TensorShape(model_input_shape)))

    predictionset = predictionset_raw.map(
        preprocess_dataset).batch(args.unet_batch_size).prefetch(2)

    # Counter variable over all tiles
    tile = 0
    progress_bar = tqdm(desc='Tiles processed', total=len(tiler))

    # create an iterator on the tf dataset
    dataset_iterator = iter(predictionset)

    while tile < len(tiler):
        inp = next(dataset_iterator)
        batch = unet.predict(inp)  # predict one batch

        # Reduce the channel dimension to binary or pseudoprobability
        if args.as_binary_mask:
            # use argmax on channels
            batch = np.argmax(batch, axis=-1)
        else:
            # use softmax on channels and retain object cannel
            batch = tf.nn.softmax(batch, axis=-1)[..., 1]

        # Write each tile in the batch to it's correct location in the output
        for i in range(batch.shape[0]):
            tiler.writeSlice(tile, batch[i, ...])
            tile += 1

        progress_bar.update(batch.shape[0])

    # Apply post Processing globaly
    if(args.with_post_processing):
        clean_floodFill(tiler.mask.image,
            high_confidence_threshold=args.high_threshold,
            low_confidence_threshold=args.low_threshold)
        removeSmallObjects(tiler.mask.image,
            probabilityThreshold=args.small_region_probability_threshold,
            size_threshold=args.small_region_size_threshold)

    print("Completed segmentation step in {} seconds".format(time.time()-seg_start_time))

    # Write to the same block in the output n5
    print('Write segmented volume', start, end, tiler.mask.image.shape)
    write_n5_block(args.output_path, args.output_data_set,
                   start, end, tiler.mask.image)
    print("Completed volume segmentation in {} seconds".format(time.time()-start_time))


if __name__ == "__main__":
    main()
