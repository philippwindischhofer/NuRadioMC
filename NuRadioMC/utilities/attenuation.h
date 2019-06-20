#include <math.h>
#include <units.h>

using namespace std;

double get_temperature(double z){
	//return temperature as a function of depth
	// from https://icecube.wisc.edu/~araproject/radio/#icetemperature
	double z2 = abs(z/utl::m);
	return 1.83415e-09*z2*z2*z2 + (-1.59061e-08*z2*z2) + 0.00267687*z2 + (-51.0696 );
}

double get_attenuation_length(double z, double frequency, int model){
	if(model == 1) {
		double t = get_temperature(z);
		double f0 = 0.0001;
		double f2 = 3.16;
		double w0 = log(f0);
		double w1 = 0.0;
		double w2 = log(f2);
		double w = log(frequency / utl::GHz);
		double b0 = -6.74890 + t * (0.026709 - t * 0.000884);
		double b1 = -6.22121 - t * (0.070927 + t * 0.001773);
		double b2 = -4.09468 - t * (0.002213 + t * 0.000332);
		double a, bb;
		if(frequency<1. * utl::GHz){
			a = (b1 * w0 - b0 * w1) / (w0 - w1);
			bb = (b1 - b0) / (w1 - w0);
		} else{
			a = (b2 * w1 - b1 * w2) / (w1 - w2);
			bb = (b2 - b1) / (w2 - w1);
		}
		return 1./exp(a +bb*w);
	} else if (model == 2) {
    // Model for Greenland. Taken from DOI: https://doi.org/10.3189/2015JoG15J057
		double att_length[] = {453.19, 461.92, 472.39, 483.73, 492.46, 502.05, 510.78, 519.50, 528.23,
		534.33, 543.06, 550.91, 561.38, 575.34, 584.06, 595.40, 605.87, 617.21, 627.68, 639.90,
		651.24, 660.83, 673.05, 683.52, 693.98, 702.71, 714.05, 728.88, 741.97, 760.29, 775.99,
		786.46, 799.54, 810.88, 823.10, 836.18, 848.40, 860.61, 871.08, 883.29, 899.87, 911.21,
		926.04, 938.25, 948.72, 960.94, 974.02, 986.24, 997.58, 1008.05, 1022.01, 1031.61,
		1043.82, 1056.91, 1065.63, 1076.98, 1088.32, 1099.66, 1113.63, 1121.48, 1133.7, 1141.55,
		1150.28, 1159.89, 1168.62, 1174.74, 1179.11, 1180.87, 1180.01, 1179.15, 1174.80, 1169.59,
		1165.25, 1160.03, 1153.94, 1149.59, 1144.37, 1140.03, 1137.42, 1134.82, 1133.97, 1135.73,
		1136.62, 1140.12, 1143.63, 1148.00, 1154.12, 1153.27, 1153.28, 1152.42};

		double depth[] = {-3038.15, -3007.84, -2988.93, -2962.42, -2947.29, -2935.95, -2913.23, -2901.89, -2890.55,
		-2875.41, -2860.27, -2845.14, -2826.22, -2811.10, -2792.18, -2773.26, -2754.34, -2739.22, -2716.51,
		-2701.39, -2682.47, -2663.55, -2644.64, -2633.30, -2614.38, -2603.04, -2580.34, -2565.23, -2538.73,
		-2512.26, -2493.36, -2470.65, -2451.74, -2440.41, -2417.71, -2395.01, -2379.89, -2357.19, -2342.06,
		-2319.35, -2296.67, -2285.34, -2262.64, -2243.73, -2221.02, -2202.11, -2179.41, -2156.70, -2126.41,
		-2118.87, -2092.38, -2069.66, -2043.16, -2024.26, -1997.74, -1967.45, -1944.74, -1918.24, -1880.37,
		-1853.86, -1827.36, -1789.47, -1755.37, -1702.31, -1641.67, -1588.60, -1524.14, -1459.67, -1395.19,
		-1330.71, -1285.18, -1194.14, -1129.64, -1061.35, -1000.64, -947.53, -883.03, -810.95, -746.46,
		-678.19, -606.12, -537.86, -458.22, -378.59, -306.54, -238.29, -173.84, -97.98, -44.89, -3.16};

		if(z < depth[0]){ return att_length[0]; }
		if(z > depth[89] ){ return att_length[89]; }

		double att_length_75_interp;
		int ind_left = 0, ind_right = 0;
		for( int i = 0; i < 89; i++ ){
			if ( z > depth[i] && z < depth[i+1] ){
				ind_left = i;
				ind_right = i+1;
			}
		}

		att_length_75_interp = att_length[ind_left] + (att_length[ind_right]-att_length[ind_left]) *
			(z-depth[ind_left])/(depth[ind_right]-depth[ind_left]);
		double att_length_f = att_length_75_interp - 0.55*utl::m * (frequency/utl::MHz - 75);

		return att_length_f;
	} else {
		std::cout << "attenuation length model " << model << " unknown" << std::endl;
		throw 0;
	}
}
