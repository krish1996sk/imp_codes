#include <iostream>
#include "benchmark.h"

#include "Halide.h"
#include "halide_image_io.h"
#include <stdio.h>

#ifdef __SSE2__
#include <emmintrin.h>
#endif

using namespace Halide::Tools;
using namespace Halide;
Var par("par");
Var in_dim("in_dim"), n("n"), unit_dim("unit_dim");
Var x("x"), y("y"), z("z"), w("w");
Var y_t("y_t"), z_t("z_t");
std::vector<Buffer<float> > params;
int out_w,out_h,out_ch,out_samples,dim;



Func Convolutional(int num_f,int f_w,int f_h,int pad,int stride, Func d_layer,int in_h,int in_w,int in_ch,int num_samples ){

    assert( (in_h + 2 * pad - f_h) % stride == 0);
    assert( (in_w + 2 * pad - f_w) % stride == 0);

    Buffer<float> W(f_w, f_h, in_ch, num_f), b(num_f);
    params.push_back(W); params.push_back(b);

            // Define forward
    RDom r(0, f_w, 0, f_h, 0, in_ch);
     
    Func forward;       // Initialize to bias
    forward(x, y, z, n) = b(z);
    forward(x, y, z, n) += W(r.x, r.y, r.z, n) *d_layer(x*stride + r.x - pad,y*stride + r.y - pad,r.z, n);

    out_w= 1 + (in_w + 2 * pad - f_w)/stride ;
    out_h =1 + (in_h + 2 * pad - f_h)/stride;
    out_ch = num_f;
    out_samples = num_samples;
    dim=4;

    return forward;



}

Func ReLU(Func d_layer,int input){
    Func forward_r;

    switch(input) {

        case 1:
            forward_r(x) = max(0, d_layer(x));
            break;
        case 2:
            forward_r(x, y) = max(0, d_layer(x, y));
            break;
        case 3:
            forward_r(x, y, z) = max(0, d_layer(x, y, z));
            break;
        case 4:
            forward_r(x, y, z, w) = max(0, d_layer(x, y, z, w));
            break;
        default:
            assert(0);
        }

    return forward_r;
}

Func MaxPooling(int p_w,int p_h,int p_stride, Func d_layer,int in_h,int in_w,int in_ch,int num_samples ){
    assert((in_h - p_h) % p_stride == 0);
    assert((in_w - p_w) % p_stride == 0);

    Func forward_Max;
    RDom r(0, p_w, 0, p_h);
    forward_Max(x, y, z, n) = maximum(d_layer(x * p_stride + r.x, y * p_stride + r.y, z, n));
    out_w =1 + ((in_w - p_w)/p_stride);
    out_h = 1 + ((in_h - p_h)/p_stride);
    out_ch = in_ch;
    dim=4;

    return forward_Max;
}

Func Flatten(int w,int h,int c,int num_samples,Func d_layer,int input){
    assert(input>= 2 && input <=4);
    Func forward_f;
    if(input==2){
        out_w = w;
        out_h=0;
        out_ch=0;
        out_samples=num_samples;
        dim =2;
        forward_f(x, n) = d_layer(x, n);
    }
    else if(input ==3){
        out_w = w * h;
        out_h=0;
        out_ch=0;
        out_samples=num_samples;
        dim =2;
        forward_f(x, n) = d_layer(x%w, (x/w), n);

    }
    else if(input ==4){
        out_w = w * h * c;
        out_h=0;
        out_ch=0;
        out_samples=num_samples;
        dim = 2;
        forward_f(x, n) = d_layer(x%w, (x/w)%h, x/(w*h), n);

    }
    return forward_f;

}

Func Affine(int num_units,int num_inputs,int num_samples,Func d_layer){
    Buffer<float> W(num_inputs, num_units), b(num_units);
    params.push_back(W); params.push_back(b);

    RDom r(0, num_inputs);
            // Initialize reduction to baises'
    Func forward_A;
    forward_A(unit_dim, n) = b(unit_dim);
            // Dot product
    forward_A(unit_dim, n) +=d_layer(r.x, n) * W(r.x, clamp(unit_dim, 0, num_units - 1));
    out_w = num_units;
    out_samples = num_samples;
    out_h=0;
    out_ch=0;
    dim =2;
    return forward_A;
}

Func SoftMax(int num_classes,int num_samples,Func d_layer){
    assert(dim== 2);
    Func forward_soft;
    Func exp_max("exp_max"), expo("expo"), normalizer("normalizer");
    RDom r(0, num_classes);
    exp_max(n) = maximum(d_layer(r.x, n));
    expo(in_dim, n) = exp(d_layer(in_dim, n) - exp_max(n));
    normalizer(n) = cast(d_layer.output_types()[0], 0);
    normalizer(n) += expo(r.x, n);
    forward_soft(in_dim, n) = expo(in_dim, n)/normalizer(n);

    out_w = num_classes;
    out_samples = num_samples;
    dim=2;
    return forward_soft;

}

Func loss(int num_classes,int num_samples,Func d_layer, Func labels){
    assert(labels.defined());
    // Check if the dimensions make sense
    assert(labels.dimensions() == 1);

    Func loss_p("loss_p");
    RDom r(0, num_samples);
    loss_p(x) = cast(d_layer.output_types()[0], 0);
    // The clamp is necessary. Otherwise, halide will assume that the
    // label can be anything during bounds inference.
    loss_p(0) += -log(d_layer(clamp(labels(r.x), 0, num_classes - 1),r.x))/num_samples;
    return loss_p;
}
             


int main(int argc, char **argv) {

    int sched = atoi(argv[1]);

    // Network structure
    // data -> conv1_1 -> relu1_1 -> conv1_2 -> relu1_2 -> pool1 ->
    // conv2_1 -> relu2_1 -> conv2_2 -> relu2_2 -> pool2 ->
    // conv3_1 -> relu3_1 -> conv3_2 -> relu3_2 -> conv3_3 -> relu3_3 -> pool3 ->
    // conv4_1 -> relu4_1 -> conv4_2 -> relu4_2 -> conv4_3 -> relu4_3 -> pool4 ->
    // conv5_1 -> relu5_1 -> conv5_2 -> relu5_2 -> conv5_3 -> relu5_3 -> pool5 ->
    // fc6-> relu6 -> droupout6-> fc7 -> relu7 -> dropout7 -> fc8 -> loss

    
    //float reg = 0.001;

    // Description of the neural network
    std::vector<Func> network;


    int N = 4; // number of samples/batch_size
    int d_w = 24; // data width
    int d_h = 24; // data height
    int ch = 3; // number of channels

    Buffer<float> data(d_w, d_h, ch, N);
    Buffer<int> labels(N);
    Func d_layer = BoundaryConditions::repeat_edge(data, 0, d_w, 0,d_h);

    int n_f_1 = 6; // number of filters
    int f_w = 3;  // filter width
    int f_h = 3;  // filter height
    int pad = (f_w-1)/2; // padding required to handle boundaries
    int stride = 1; // stride at which the filter evaluated

    out_w = d_w;
    out_h = d_h;
    out_ch = ch;
    out_samples= N;
    dim =4;

    Func conv1_1  = Convolutional(n_f_1, f_w, f_h, pad,stride, d_layer,out_w,out_h,out_ch,out_samples);
    network.push_back(conv1_1);


    Func relu1_1= ReLU(conv1_1,dim);
    network.push_back(relu1_1);

    Func conv1_2 = Convolutional(n_f_1, f_w, f_h, pad,stride, relu1_1,out_w,out_h,out_ch,out_samples);
    network.push_back(conv1_2);

    Func relu1_2 = ReLU(conv1_2,dim);
    network.push_back(relu1_2);

    

    int p_w = 2; // pooling width
    int p_h = 2; // pooling height
    int p_stride = 2; // pooling stride_
    Func pool1 = MaxPooling(p_w,p_h,p_stride,relu1_2,out_w,out_h,out_ch,out_samples);
    network.push_back(pool1);
    

    Func flatten = Flatten(out_w,out_h,out_ch,out_samples,pool1,dim);
    network.push_back(flatten);

    flatten.compute_root().store_root();

    int C=2;
    Func fc6 = Affine(C,out_w,out_samples,flatten);
    network.push_back(fc6);
    //fc6.store_root();

    Func softm = SoftMax(out_w,out_samples,fc6);
    network.push_back(softm);


    Func acc = loss(out_w,out_samples,softm, Func(labels));
    Buffer<float> scores(C, N), loss(1);

    softm.bound(softm.args()[0], 0, C).bound(softm.args()[1], 0, N);
    acc.bound(acc.args()[0], 0, 1);

    /*softm->forward.estimate(softm->forward.args()[0], 0, C).
                   estimate(softm->forward.args()[1], 0, N);
    acc.estimate(acc.args()[0], 0, 1);*/

    std::vector<Func> test_outs;
    test_outs.push_back(acc);
    test_outs.push_back(softm);
    Pipeline test(test_outs);

    Target target = get_target_from_environment();
    if (sched == -2) {
        target.set_feature(Halide::Target::CUDACapability35);
        //target.set_feature(Halide::Target::CUDA);
        //target.set_feature(Halide::Target::Debug);
    }

    if (sched == -1 || sched == -2)
        test.compile_jit(target);
    else
        test.compile_jit(target);

    double best = benchmark(5, 3, [&]() { test.realize({loss, scores}); scores.copy_to_host();});
    std::cout << "runtime: " << best * 1e3 << std::endl;


    Buffer<float> result1 = softm.realize(out_w,out_samples);



                          
}
