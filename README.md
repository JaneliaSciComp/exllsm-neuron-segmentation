# ExLLSM Neuron Segmentation


This is an adaptation of Linus Meienberg's [tool](https://github.com/randomstructures/ExLSM-Image-Segmentation) for segmenting neurons in large scale volumetric images generated via expansion microscopy and lattice light-sheet imaging (ExLLSM). This tool utilizes a trained U-Net model to segment neurons from background and non-specific antibody labels. 

Code to train a U-Net model and to prepare training and evaluation datasets is provided here. To use a trained model for neuron segmentation, the code is integrated into the [ExLLSM Circuit Reconstruction Pipeline](https://github.com/JaneliaSciComp/exllsm-circuit-reconstruction) and currently meant to be run there, inside of a Docker container. However, a brief overview of how to use the tool outside of the ExLLSM Circuit Reconstruction Pipeline is included here as well.

## Quick Start

First setup a conda environment using the following command:
```
conda create -n neuron-segmentation python=3.9
conda env update -n neuron-segmentation -f conda-requirements.yml
```
then activate it:
`
conda activate neuron-segmentation
`
## Model training and evaluation

There are two ways to use the tools to prepare training and evaluation datasets, train a model, and evaluate model performance. One is to invoke the tool from the command line using the corresponding command ending in '_cmd.py': `datasetPreparation_cmd.py`, `training_cmd.py` and/or `evaluation_cmd.py`. Alternatively, the tools can be used without the '_cmd' suffix from a Jupyter notebook.

### Dataset Preparation

Tool for peparing training and evaluation datasets. 

This tool prepares an HDF5 dataset that can be used for training a model or for evaluating model performance. Input datsets (Regions) composed of a raw data and ground truth data channels stored in different groups in HDF5 format are required. The Regions are automatically subdivided into a grid of potential Training Examples. Because much of the 3D volume may be empty space, a threshold is set to identify Training Examples with signal. An above-threshold-ratio is set to determine the percentage of Training Examples/Region that should be above the set threshold (i.e. Training Examples with and without signal).

* Regions = crops that are manually extracted from a image volume; stored at HDF5 datasets where channels are in different groups
* Training examples = small crops automatically extracted from Regions using this script

Usage: 

     python datasetPreparation_cmd.py --region-dir /REGION-DIR/ --dataset-dir /DATASET-DIR/ --output-dir /DATASET-DIR/ --above-threshold-ratio 0.9 --samples-per-region 50

#### Required Parameters
| Argument   | Default | Description                                                                           |
|------------|---------|---------------------------------------------------------------------------------------|
| --region-dir |  | directory where input datasets in HDF5 format are located |
| --output-dir |  | output directory |
| --dataset-dir |  | directory where output HDF5 dataset is to be saved |
| --above-threshold-ratio | 0.9 | ratio of Training Examples above the set threshold versus training examples below the set threshold to be included |
| --samples-per-region | 50 | number of Training Examples per Region to include in the dataset |

### Model Training

This tool will train a U-Net model using an input dataset generated via Dataset Preparation (above).

Usage: 

     python training_cmd.py --training-dataset /TRAINING-DATASET-DIR/training-dataset.h5 --output-dir /OUTPUT-DIR/ --model-name TRAINEDMODEL.h5 
     
#### Required Parameters
| Argument   | Default | Description                                                                           |
|------------|---------|---------------------------------------------------------------------------------------|
| --training-dataset |  | Path to training dataset in HDF5 format  |
| --output-dir |  | output directory |
| --model-name |  | name of trained HDF5 model |

#### Optional Parameters
| Argument   | Default | Description                                                                           |
|------------|---------|---------------------------------------------------------------------------------------|
| --resume | False |  option to resume training a previously trained model  |
| --pre-trained-model |  | Path to pre-trained model in HDF5 format if --resume True |
| --set_gpu_mem_growth | False | if True, sets the GPU memory growth |

#### Architecture Parameters
| Argument   | Default | Description                                                                           |
|------------|---------|---------------------------------------------------------------------------------------|
| --initial-filters | 4 |  The number of filter maps in the first convolutional operation  |
| --bottleneck-dropout-rate | 0.2  |    |
| --spatial-dropout | False |    |
| --spatial-dropout-rate | 0.2 |    |

#### Training Parameters
| Argument   | Default | Description                                                                           |
|------------|---------|---------------------------------------------------------------------------------------|
| --test-fraction | 0.2  | Fraction of training examples set aside for validation   |
| --no-affine | False  |    |
| --with-elastic-deform | False  |    |
| --with-occlusions | False |    |
| --occulsion-size | 40 |    |
| --epochs | 10 |    |
| --object-class-weight | 5 |    |
| --dice-weight | 0.3 |    |
| --batch-size | 1 |    |
| --with-visualization-sample | False |    |

### Model Evaluation

To appropriately evaluate the model performance it should be compared to ground truth data from independent samples (brains/animals) not involved in training. 

It is recommended that the trained model is used via the [ExLLSM Circuit Reconstruction Pipeline](https://github.com/JaneliaSciComp/exllsm-circuit-reconstruction) where additional recommended post-U-Net processing steps not included here can be used. To evaluate the performance of a model run via the ExLLSM Circuit Reconstruction Pipeline to ground truth data from independent samples, the ExLLSM_unet_performance_evaluate.py script from the [ExLLSM Synapse Detection](https://github.com/JaneliaSciComp/SynapseDetectorDNN) repository can be used.

However, if desired, the perforance of a model (without the recommended post-U-Net processing steps) can be evaluated here using the evaluation tool.

Usage: 

     python evaluation_cmd.py --dataset /EVAL-DATASET-DIR/evaluation-dataset.h5 --model-path /MODEL-DIR/trained-model.h5 --output-dir /OUTPUT-DIR/

#### Required Parameters
| Argument   | Default | Description                                                                           |
|------------|---------|---------------------------------------------------------------------------------------|
| --dataset |  | Path to evaluation dataset in HDF5 format |
| --output-dir |  | output directory |
| --model-path |  | Path to trained HDF5 model |

#### Optional Parameters
Additional optional parameters can be found in the script. These include the number of examples from the evaluation dataset to be used for evaluation (default 40) and the interval to print performance examples for visualization (default 10).

### Image Segmentation

It is recommended that the trained model is used via the [ExLLSM Circuit Reconstruction Pipeline](https://github.com/JaneliaSciComp/exllsm-circuit-reconstruction) where additional recommended post-U-Net processing steps not included here can be used. Details on how to run the pipeline and suggested post-U-Net processing steps and parameters can be found there. 

Below is an example of how to volume segmentation without the ExLLSM Circuit Reconstruction Pipeline:
```
python volumeSegmentation.py \
    -i /test/ExM/P1_pIP10/20200808/images/export_substack_crop.n5 \
    -id /c1/s0 \
    -o /results/test/Q1seg.n5 \
    -od /segmented/s0 \
    -m /model_location/trained_models/neuron4_p2/neuron4_150.h5 \
    --image_shape 10325,6150,2560 \
    --start 0,0,0 \
    --end 250,250,250 \
    --set_gpu_mem_growth \
    --unet_batch_size 1 \
    --model_input_shape 220,220,220 \
    --model_output_shape 132,132,132 \
    --with_post_processing \
    --high_threshold 0.98 \
    --low_threshold 0.2 \
    --small_region_probability_threshold 0.9 \
    --small_region_size_threshold 1000
```

Segmenting the volume can be preceded by calculating the global scaling factor (not recommended) using:
```
python volumeScalingFactor.py \
    -i /test/ExM/P1_pIP10/20200808/images/export_substack_crop.n5 \
    -d /c1/s0 \
    -p 0.1 \
    --partition_size 396,396,396 \
    --start 0,0,0 \
    --end 250,250,250
```
